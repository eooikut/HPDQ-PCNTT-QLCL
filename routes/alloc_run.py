from flask import Blueprint, app, render_template, current_app, request, jsonify
import pandas as pd
import os
import threading
import numpy as np
import json
import math
import db  # Module db.py
import requests
from apscheduler.schedulers.background import BackgroundScheduler
import atexit
from datetime import datetime , timedelta
import time
import requests
import pymysql 
alloc_run_bp = Blueprint('alloc_run_bp', __name__)
upload_lock = threading.Lock()
@alloc_run_bp.route('/allocation_run', methods=['GET'])
def allocation_run_page():
    """Trang Chạy Phân bổ (Chọn TDC -> Chạy)"""
    return render_template('allocation_run.html')
@alloc_run_bp.route('/api/run_batch_allocation', methods=['POST'])
def run_batch_allocation():
    try:
        request_list = request.json 
        conn = db.get_connection()
        
        # 1. Lấy dữ liệu kho (như cũ)
        query = "SELECT coil_id, scores, grade, allocated_to, weight, target_thick, target_width FROM coil_data"
        rows = conn.execute(query).fetchall()
        conn.close()
        
        all_inventory = []
        for r in rows:
            alloc_val = r['allocated_to']
            is_free = (alloc_val is None) or (str(alloc_val).strip() == '')
            if is_free:
                all_inventory.append({
                    'coil_id': r['coil_id'], 
                    'scores': json.loads(r['scores']) if r['scores'] else {}, 
                    'grade': str(r['grade']).strip().upper() if r['grade'] else 'UNKNOWN',
                    'weight': r['weight'] or 0,
                    'thick': r['target_thick'] or 0,
                    'width': r['target_width'] or 0
                })
        
        used_coil_ids = set() 
        final_flat_list = []  

        for req in request_list:
            cust_name = req.get('customer_name', 'Unknown')
            target_grade = str(req.get('grade', '')).strip().upper()
            qty_req = int(req.get('qty', 0))
            criteria = req.get('criteria', [])
            req_thick = float(req.get('thick', 0)) # Dày yêu cầu
            req_width = float(req.get('width', 0)) # Rộng yêu cầu
            grade_inventory = []
            for x in all_inventory:
                if x['coil_id'] in used_coil_ids: continue
                if x['grade'] != target_grade: continue
                
                # Check Quy cách (Nếu request có yêu cầu)
                if req_thick > 0 and abs(x['thick'] - req_thick) > 0.0: continue # Sai lệch dày > 0.05 bỏ
                if req_width > 0 and abs(x['width'] - req_width) > 0: continue 
                req_min_w = float(req.get('min_weight', 0))
                req_max_w = float(req.get('max_weight', 0))
                current_w = x.get('weight', 0)

                # Nếu có yêu cầu Min Weight mà cuộn nhỏ hơn -> Bỏ
                if req_min_w > 0 and current_w < req_min_w: continue
                # Nếu có yêu cầu Max Weight mà cuộn lớn hơn -> Bỏ
                if req_max_w > 0 and current_w > req_max_w: continue   # Sai lệch rộng > 5mm bỏ
                
                grade_inventory.append(x)
            
            candidates = []
            for item in grade_inventory:
                scores = item['scores']
                total_penalty = 0 
                sort_diffs = []   
                failed_criteria = {} 

                for crit in criteria:
                    defect_key = crit['defect']
                    try: target_val = int(crit['target'])
                    except: target_val = 1
                    allowed_vals = crit['range']     
                    actual_score = scores.get(defect_key, 1)
                    
                    if actual_score in allowed_vals:
                        diff = 0
                    else:
                        min_dist = min([abs(actual_score - v) for v in allowed_vals])
                        total_penalty += min_dist
                        diff = min_dist
                        failed_criteria[defect_key] = True
                    sort_diffs.append(abs(actual_score - target_val))

                if total_penalty <= 100: 
                    c_item = item.copy()
                    c_item.update({
                        'penalty': total_penalty,       
                        'sort_keys': tuple(sort_diffs), 
                        'failed': failed_criteria,
                        'customer_alloc': cust_name,
                        'order_alloc': req.get('so_number', 'N/A'),
                        # [THÊM MỚI]: Gắn ID của dòng TDC để phân biệt các dòng hàng trong cùng 1 SO
                        'tdc_line_id': req.get('id'), 
                        # [THÊM MỚI]: Gắn quy cách yêu cầu để dễ hiển thị
                        'req_thick': req_thick,
                        'req_width': req_width,
                        'material_desc': f"{req_thick}x{req_width}"
                    })
                    candidates.append(c_item)

            candidates.sort(key=lambda x: (x['penalty'], x['sort_keys']))

            limit_show = max(qty_req * 3, 50) 

            allocated_view = candidates[:limit_show] 


            temp_take = candidates[:qty_req]
            for item in temp_take:
                used_coil_ids.add(item['coil_id'])

            
            final_flat_list.extend(allocated_view)
            
        return jsonify({
            'status': 'success',
            'allocated': final_flat_list,
            'msg': f"Tìm thấy {len(final_flat_list)} ứng viên tiềm năng."
        })

    except Exception as e:
        return jsonify({'status': 'error', 'msg': str(e)})
@alloc_run_bp.route('/api/run_allocation', methods=['POST'])
def run_allocation():
    try:
        req = request.json
        target_grade = req.get('grade')
        qty_req = int(req.get('qty', 10))
        criteria_list = req.get('criteria', [])
        
        conn = db.get_connection()
        query = "SELECT coil_id, scores FROM coil_data WHERE grade = ? AND (allocated_to IS NULL OR allocated_to = '')"
        rows = conn.execute(query, (target_grade,)).fetchall()
        conn.close()

        candidates = []
        for r in rows:
            if not r['scores']: continue
            scores = json.loads(r['scores'])
            
            total_penalty = 0 
            sort_diffs = []   
            failed_criteria = {} 

            for crit in criteria_list:
                defect_key = crit['defect']
                target_val = int(crit['target'])
                allowed_vals = crit['range']     
                actual_score = scores.get(defect_key, 1)
                
                if actual_score in allowed_vals:
                    diff = 0
                else:
                    # Tính điểm phạt nếu nằm ngoài vùng chấp nhận
                    min_dist = min([abs(actual_score - v) for v in allowed_vals])
                    total_penalty += min_dist
                    diff = min_dist
                    failed_criteria[defect_key] = True
                
                dist_to_target = abs(actual_score - target_val)
                sort_diffs.append(dist_to_target)
            
            # Chỉ lấy các cuộn có độ lệch chấp nhận được (<= 10)
            if total_penalty <= 10: 
                candidates.append({
                    'coil_id': r['coil_id'],
                    'scores': scores,
                    'penalty': total_penalty,       
                    'sort_keys': tuple(sort_diffs), 
                    'failed': failed_criteria       
                })

        # --- LOGIC MỚI: PHÂN LOẠI & LỌC ---
        
        # 1. Tách làm 2 nhóm
        perfect_candidates = [c for c in candidates if c['penalty'] == 0]
        suggestion_candidates = [c for c in candidates if c['penalty'] > 0]
        
        # Sắp xếp nội bộ từng nhóm (Ưu tiên sát target nhất)
        perfect_candidates.sort(key=lambda x: x['sort_keys'])
        suggestion_candidates.sort(key=lambda x: (x['penalty'], x['sort_keys']))
        
        final_list = []
        msg = ""

        # 2. Kiểm tra điều kiện số lượng
        if len(perfect_candidates) >= qty_req:
            # TRƯỜNG HỢP 1: Đủ hàng chuẩn -> Chỉ lấy hàng chuẩn
            # (Trả về toàn bộ hàng chuẩn tìm thấy để user tha hồ chọn)
            final_list = perfect_candidates
            msg = f"✅ Tìm thấy {len(final_list)} cuộn ĐẠT CHUẨN (Đủ yêu cầu)."
        else:
            # TRƯỜNG HỢP 2: Thiếu hàng -> Lấy hết hàng chuẩn + Gợi ý bù vào
            missing = qty_req - len(perfect_candidates)
            # Lấy thêm gợi ý = số còn thiếu + 10 cuộn dư ra để chọn
            limit_suggestions = missing + 10 
            
            top_suggestions = suggestion_candidates[:limit_suggestions]
            final_list = perfect_candidates + top_suggestions
            
            msg = f"⚠️ Chỉ có {len(perfect_candidates)} cuộn chuẩn. Hệ thống gợi ý thêm {len(top_suggestions)} cuộn tiệm cận."

        return jsonify({
            'status': 'success',
            'total_found': len(candidates), # Tổng tìm thấy trong kho
            'perfect_count': len(perfect_candidates),
            'allocated': final_list, # Danh sách trả về frontend đã được lọc
            'msg': msg
        })

    except Exception as e: return jsonify({'status': 'error', 'msg': str(e)})
@alloc_run_bp.route('/api/confirm_allocation', methods=['POST'])
def confirm_allocation():
    try:
        req = request.json
        coil_ids = req.get('coil_ids', [])
        tdc_name = req.get('tdc_name')
        so_number = req.get('so_number') # [MỚI] Nhận số SO
        
        if not coil_ids: return jsonify({'status': 'error', 'msg': 'Rỗng'})

        conn = db.get_connection()
        import datetime
        now = datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        # Cập nhật cả allocated_to VÀ allocated_order
        for cid in coil_ids:
        
            conn.execute("""
                UPDATE coil_data 
                SET allocated_to = ?, allocated_order = ?, allocated_at = ? 
                WHERE coil_id = ?
            """, (tdc_name, so_number, now, cid))
            
        conn.commit()
        conn.close()
        return jsonify({'status': 'success', 'msg': 'Đã chốt đơn thành công!'})
    except Exception as e: return jsonify({'status': 'error', 'msg': str(e)})

@alloc_run_bp.route('/api/update_db_schema', methods=['GET'])
def update_db_schema():
    try:
        conn = db.get_connection()
        msg = []

        # 1. Cập nhật bảng coil_data (Dữ liệu cuộn)
        try: 
            conn.execute("ALTER TABLE coil_data ADD COLUMN allocated_to TEXT")
            msg.append("Đã thêm allocated_to")
        except: pass
        
        try: 
            conn.execute("ALTER TABLE coil_data ADD COLUMN allocated_at TEXT")
            msg.append("Đã thêm allocated_at")
        except: pass

        # 2. Cập nhật bảng customer_orders (Cấu hình Đơn hàng/TDC)
        # [QUAN TRỌNG]: Thêm cột so_number để sửa lỗi "no such column: so_number"
        try: 
            conn.execute("ALTER TABLE customer_orders ADD COLUMN so_number TEXT")
            msg.append("Đã thêm so_number")
        except: pass

        # 3. (Tùy chọn) Thêm các cột quy cách nếu thiếu
        for col in ['target_thick', 'target_width', 'min_weight', 'max_weight', 'req_weight_total']:
            try: 
                conn.execute(f"ALTER TABLE customer_orders ADD COLUMN {col} REAL")
            except: pass
        try: conn.execute("ALTER TABLE coil_data ADD COLUMN allocated_order TEXT")
        except: pass
        conn.commit()
        conn.close()
        
        if not msg: return jsonify({'msg': 'DB đã cập nhật đầy đủ, không cần sửa gì.'})
        return jsonify({'msg': 'Cập nhật thành công: ' + ', '.join(msg)})
        
    except Exception as e: return jsonify({'msg': str(e)})
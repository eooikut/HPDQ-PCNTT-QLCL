
from flask import Blueprint, app, render_template, current_app, request, jsonify
import pandas as pd
import threading
import numpy as np
import json
import db  # Module db.py
from apscheduler.schedulers.background import BackgroundScheduler

tdc_bp = Blueprint('tdc_bp', __name__)
upload_lock = threading.Lock()
@tdc_bp.route('/tdc_manager', methods=['GET'])
def tdc_manager_page():
    """Trang Quản lý cấu hình TDC (Tạo/Sửa/Lưu)"""
    return render_template('tdc_manager.html')
@tdc_bp.route('/api/save_tdc_batch', methods=['POST'])
def save_tdc_batch():
    try:
        req = request.json
        # 1. Thông tin chung (Master)
        customer = req.get('customer_name', '').strip()
        so_number = req.get('so_number', '').strip()
        grade = req.get('grade', '').strip()
        criteria_json = json.dumps(req.get('criteria', []))
        # 2. Danh sách quy cách (Details)
        items = req.get('items', []) # List các dict {id, thick, width, ...}
        if not customer or not so_number:
            return jsonify({'status': 'error', 'msg': 'Thiếu Tên Khách hoặc Số SO!'})
        conn = db.get_connection()
        count_updated = 0
        count_inserted = 0

        for item in items:
            item_id = item.get('id') # Nếu có ID là update, không là insert
            
            # Lấy dữ liệu từng dòng
            try: thick = float(item.get('thick', 0))
            except: thick = 0
            try: width = float(item.get('width', 0))
            except: width = 0
            try: qty = int(item.get('qty', 0))
            except: qty = 0
            try: total_w = float(item.get('total_weight', 0))
            except: total_w = 0
            try: min_w = float(item.get('min_weight', 0))
            except: min_w = 0
            try: max_w = float(item.get('max_weight', 0))
            except: max_w = 0

            if item_id:
                # UPDATE: Cập nhật quy cách VÀ cập nhật luôn cả tiêu chuẩn (nếu user có sửa ở Master)
                sql = """
                    UPDATE customer_orders 
                    SET customer_name=?, so_number=?, grade=?, criteria_json=?,
                        target_thick=?, target_width=?, qty_req=?, req_weight_total=?,
                        min_weight=?, max_weight=?
                    WHERE id=?
                """
                conn.execute(sql, (customer, so_number, grade, criteria_json, thick, width, qty, total_w, min_w, max_w, item_id))
                count_updated += 1
            else:
                # INSERT: Thêm dòng quy cách mới cho SO này
                sql = """
                    INSERT INTO customer_orders 
                    (customer_name, so_number, grade, criteria_json, target_thick, target_width, qty_req, req_weight_total, min_weight, max_weight)
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """
                conn.execute(sql, (customer, so_number, grade, criteria_json, thick, width, qty, total_w, min_w, max_w))
                count_inserted += 1
        
        conn.commit()
        conn.close()
        
        return jsonify({
            'status': 'success', 
            'msg': f'Đã lưu SO: {so_number}.\nCập nhật: {count_updated} dòng.\nThêm mới: {count_inserted} dòng.'
        })
            
    except Exception as e:
        return jsonify({'status': 'error', 'msg': str(e)})
@tdc_bp.route('/api/save_tdc', methods=['POST'])
def save_tdc_config():
    try:
        req = request.json
        order_id = req.get('id')
        
        # [MỚI] Nhận thêm các tham số quy cách
        thick = float(req.get('thick', 0))
        width = float(req.get('width', 0))
        min_w = float(req.get('min_weight', 0))
        max_w = float(req.get('max_weight', 0))
        total_w_req = float(req.get('req_weight', 0)) # Tổng tấn yêu cầu

        # Cập nhật câu lệnh SQL trong db.py hoặc viết trực tiếp ở đây
        conn = db.get_connection()
        
        criteria_json = json.dumps(req.get('criteria', []))
        
        if order_id:
            # UPDATE
            sql = """
                UPDATE customer_orders 
                SET customer_name=?, grade=?, qty_req=?, criteria_json=?,
                    target_thick=?, target_width=?, min_weight=?, max_weight=?, req_weight_total=?
                WHERE id=?
            """
            params = (req['customer_name'], req['grade'], req['qty'], criteria_json, 
                      thick, width, min_w, max_w, total_w_req, order_id)
        else:
            # INSERT
            sql = """
                INSERT INTO customer_orders 
                (customer_name, grade, qty_req, criteria_json, target_thick, target_width, min_weight, max_weight, req_weight_total)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
            """
            params = (req['customer_name'], req['grade'], req['qty'], criteria_json, 
                      thick, width, min_w, max_w, total_w_req)
            
        conn.execute(sql, params)
        conn.commit()
        conn.close()
        
        return jsonify({'status': 'success', 'msg': 'Đã lưu cấu hình TDC kèm Quy cách!'})
            
    except Exception as e: return jsonify({'status': 'error', 'msg': str(e)})
@tdc_bp.route('/api/delete_tdc', methods=['POST'])
def delete_tdc_config():
    try:
        req = request.json
        order_id = req.get('id')
        if not order_id: return jsonify({'status': 'error', 'msg': 'Thiếu ID'})
        
        if db.delete_customer_order(order_id):
            return jsonify({'status': 'success', 'msg': 'Đã xóa TDC thành công'})
        else:
            return jsonify({'status': 'error', 'msg': 'Lỗi khi xóa'})
    except Exception as e: return jsonify({'status': 'error', 'msg': str(e)})
@tdc_bp.route('/api/get_order_history', methods=['GET'])
def get_order_history():
    try:
        conn = db.get_connection()
        rows = conn.execute("""
            SELECT * FROM customer_orders 
            ORDER BY customer_name, so_number, created_at DESC
        """).fetchall()
        conn.close()
        
        history = []
        for r in rows:
            history.append({
                'id': r['id'],
                'customer_name': r['customer_name'],
                'so_number': r['so_number'] or 'NO_SO',
                'grade': r['grade'],
                'qty_req': r['qty_req'],
                'criteria': json.loads(r['criteria_json']) if r['criteria_json'] else [],
                'thick': r['target_thick'] or 0,
                'width': r['target_width'] or 0,
                'req_weight': r['req_weight_total'] or 0,
                'min_weight': r['min_weight'],
                'max_weight': r['max_weight']
            })
        return jsonify(history)
    except Exception as e: return jsonify([])
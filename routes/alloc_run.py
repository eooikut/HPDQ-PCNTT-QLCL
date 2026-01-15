from flask import Blueprint, render_template, request, jsonify
import json
import db  # Module db.py
import threading
import re
alloc_run_bp = Blueprint('alloc_run_bp', __name__)
import re

@alloc_run_bp.route('/api/sap/get_so_list', methods=['GET'])
def get_sap_so_list():
    try:
        conn = db.get_connection()
        query = """
        SELECT DISTINCT 
            [Sales Document] as so_number, 
            [Customer] as customer_name,
            [PO.] as po_number
        FROM [factory].[dbo].[so] WITH (NOLOCK)
        ORDER BY [Sales Document] DESC
        """
        cursor = conn.cursor()
        cursor.execute(query)
        rows = db.fetchall_as_dict(cursor) # Hàm helper của bạn
        conn.close()
        return jsonify({'status': 'success', 'data': rows})
    except Exception as e:
        return jsonify({'status': 'error', 'msg': str(e)})

# --- API MỚI: Lấy chi tiết Material và Parse thông tin ---
@alloc_run_bp.route('/api/sap/get_so_items', methods=['POST'])
def get_sap_so_items():
    try:
        so_number = request.json.get('so_number')
        if not so_number: return jsonify({'status':'error', 'msg':'Thiếu số SO'})

        conn = db.get_connection()
        # Lấy dữ liệu theo SO
        query = """
        SELECT 
            [Material] as material_code,
            [Item Description] as description,
            [Quantity (KG)] as total_qty,
            [Shipped Quantity (KG)] as shipped_qty,
            [Customer] as customer_name
        FROM [factory].[dbo].[so] WITH (NOLOCK)
        WHERE [Sales Document] = ?
        """
        cursor = conn.cursor()
        cursor.execute(query, (so_number,))
        rows = db.fetchall_as_dict(cursor)
        conn.close()
        # --- LOGIC PARSE ITEM DESCRIPTION ---
        results = []
        for r in rows:
            desc = r['description']
            thick = 0.0
            width = 0.0
            grade = ""
            dim_match = re.search(r'(\d+(?:\.\d+)?)\s*[xX]\s*(\d+(?:\.\d+)?)', desc)
            
            if dim_match:
                try:
                    thick = float(dim_match.group(1))
                    width = float(dim_match.group(2))
                    
                    # 2. Logic đoán Mác thép (Grade)
                    # Thường Mác thép nằm sau kích thước hoặc ở cuối chuỗi
                    # Cách đơn giản: Lấy phần chuỗi SAU kích thước và làm sạch
                    remaining = desc[dim_match.end():].strip()
                    # Tách các từ, thường mác thép là từ đầu tiên sau kích thước (VD: SAE1006)
                    if remaining:
                        parts = remaining.split()
                        grade = parts[0] # Lấy từ đầu tiên (SPHC, SAE1006, SS400...)
                except:
                    pass

            # Tính khối lượng cần (Còn lại)
            needed_qty = float(r['total_qty'] or 0) - float(r['shipped_qty'] or 0)
            if needed_qty < 0: needed_qty = 0

            results.append({
                'material_code': r['material_code'],
                'description': desc,
                'thick': thick,
                'width': width,
                'grade': grade, # Mác thép parse được
                'customer_name': r['customer_name'],
                'req_weight': needed_qty # Tự động trừ đi lượng đã ship
            })

        return jsonify({'status': 'success', 'data': results})
    except Exception as e:
        return jsonify({'status': 'error', 'msg': str(e)})
@alloc_run_bp.route('/allocation_run', methods=['GET'])
def allocation_run_page():
    """Trang Chạy Phân bổ"""
    return render_template('allocation_run.html')

@alloc_run_bp.route('/api/run_batch_allocation', methods=['POST'])
def run_batch_allocation():
    try:
        req_items = request.json.get('items', [])
        conn = db.get_connection()
        cursor = conn.cursor()
        query_tdc = """
            SELECT m.id as master_id, m.tdc_code, m.customer_name, m.grade, 
                v.criteria_json, v.id as version_id
            FROM tdc_master m
            JOIN tdc_versions v ON m.id = v.master_id
            WHERE v.status = 'Active'
            AND CAST(GETDATE() AS DATE) >= v.valid_from 
            AND (v.valid_to IS NULL OR CAST(GETDATE() AS DATE) <= v.valid_to) 
        """
        cursor.execute(query_tdc)
        active_tdcs = db.fetchall_as_dict(cursor)
        tdc_map = {row['master_id']: dict(row) for row in active_tdcs}

        cursor.execute("SELECT coil_id, scores, grade, weight, target_thick, target_width FROM coil_data WITH (NOLOCK) WHERE (allocated_to IS NULL OR allocated_to = '')")
        inventory_rows = db.fetchall_as_dict(cursor)
        conn.close()

        inventory = []
        for r in inventory_rows:
            item = dict(r)
            item['scores'] = json.loads(item['scores']) if item['scores'] else {}
            item['grade'] = str(item['grade']).strip().upper()
            item['weight'] = float(item['weight']) if item['weight'] is not None else 0.0
            item['thick'] = float(item['target_thick']) if item['target_thick'] else 0.0
            item['width'] = float(item['target_width']) if item['target_width'] else 0.0
            inventory.append(item)

        final_results = []
        used_coil_ids = set()

        # --- 2. XỬ LÝ TỪNG DÒNG YÊU CẦU ---
        for req in req_items:
            try:
                so_number = req.get('so_number', 'N/A')
                tdc_id = int(req.get('tdc_id', 0))
                req_thick = float(req.get('thick', 0))
                req_width = float(req.get('width', 0))
                req_weight_target = float(req.get('req_weight', 0))
                req_min_w = float(req.get('min_weight', 0))
                req_max_w = float(req.get('max_weight', 0))

                tdc_info = tdc_map.get(tdc_id)
                if not tdc_info: continue
                
                target_grade = tdc_info['grade']
                cust_name = tdc_info['customer_name']
                criteria_list = json.loads(tdc_info['criteria_json']) if tdc_info['criteria_json'] else []
                
                TOTAL_CRITERIA_COUNT = len(criteria_list)
                CRITICAL_THRESHOLD = 15

                candidates = []
                current_weight_sum = 0

                for coil in inventory:
                    if coil['coil_id'] in used_coil_ids: continue
                    if coil['grade'] != target_grade: continue
                    if abs(coil['thick'] - req_thick) > 0.00: continue 
                    if abs(coil['width'] - req_width) > 0.0: continue
                    if req_min_w > 0 and coil['weight'] < req_min_w: continue
                    if req_max_w > 0 and coil['weight'] > req_max_w: continue

                    total_penalty = 0
                    failed_reasons = [] 
                    match_type = 'PERFECT'
                    is_rejected = False 
                    met_count = 0
                    sort_priority_list = [] 
                    
                    scores = coil['scores']
                    
                    for idx, crit in enumerate(criteria_list):
                        defect_key = crit['defect']
                        # Lấy tên tiếng Việt (nếu bạn đã thêm map như bài trước)
                        defect_name = crit.get('name_vi', defect_key) 
                        
                        val = scores.get(defect_key, 0)
                        allowed_range = crit.get('range', [])
                        target = crit.get('target', 1)
                        
                        weight = TOTAL_CRITERIA_COUNT - idx 
                        current_dist = 0 # Độ lệch của tiêu chí này
                        
                        if val == 0:
                            # --- MISSING ---
                            penalty = weight * 25
                            total_penalty += penalty
                            failed_reasons.append(f"{defect_name}:Thiếu")
                            match_type = 'MISSING_DATA'
                            current_dist = 99 # Gán độ lệch lớn để đẩy xuống đáy khi sort phân cấp
                        
                        elif val in allowed_range:
                            # --- PASS ---
                            met_count += 1
                            current_dist = 0 # Hoàn hảo = 0
                        
                        else:
                            # --- FAIL / OUT OF RANGE ---
                            dist = abs(val - target)
                            current_dist = dist 
                            if idx < CRITICAL_THRESHOLD:
                                is_rejected = True
                                break 
                            else:
                                penalty = weight * dist * 5
                                total_penalty += penalty
                                failed_reasons.append(f"{defect_name}:C{val}(Lệch {dist})")
                                match_type = 'PROP_MISMATCH'
                        
                        sort_priority_list.append(current_dist)

                    if is_rejected: continue

                    c_item = coil.copy()
                    match_pct = round((met_count / TOTAL_CRITERIA_COUNT) * 100, 1) if TOTAL_CRITERIA_COUNT > 0 else 0
                    
                    c_item.update({
                        'penalty': total_penalty,
                        'sort_priority': tuple(sort_priority_list), # [QUAN TRỌNG] Convert sang Tuple để sort
                        'match_type': match_type,
                        'customer_alloc': cust_name,
                        'so_number': so_number,
                        'match_ratio': f"{met_count}/{TOTAL_CRITERIA_COUNT}", 
                        'match_pct': match_pct,
                        'failed_msg': ', '.join(failed_reasons)
                    })
                    candidates.append(c_item)

                candidates.sort(key=lambda x: (
                    0 if x['penalty'] == 0 else 1, 
                    x['penalty'], 
                    x['sort_priority'], 
                    -x['match_pct']
                ))

                # --- 4. CHỌN CUỘN ---
                for cand in candidates:
                    final_results.append(cand) 
                    current_weight_sum += cand['weight']
                    used_coil_ids.add(cand['coil_id'])
                    if current_weight_sum >= req_weight_target: break
            
            except Exception as ex: 
                print(f"Lỗi Alloc: {ex}")
                continue

        return jsonify({'status': 'success', 'allocated': final_results})
    except Exception as e:
        return jsonify({'status': 'error', 'msg': str(e)})


@alloc_run_bp.route('/api/confirm_multi_so', methods=['POST'])
def confirm_multi_so():
    conn = None
    try:
        req = request.json
        alloc_list = req.get('allocations', [])
        so_meta_list = req.get('so_meta', [])
        current_user = req.get('user_name', 'QC_User')
        if not alloc_list:
            return jsonify({'status': 'error', 'msg': 'Danh sách phân bổ trống!'})

        conn = db.get_connection()
        cursor = conn.cursor()
        
        import datetime
        now = datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")

        # --- GIAI ĐOẠN 1: CẬP NHẬT CẤU TRÚC ĐƠN HÀNG (HEADER & DETAILS) ---
        for meta in so_meta_list:
            so_number = str(meta.get('so_number')).strip()
            cust_name = meta.get('customer_name')
            material_code = meta.get('material', '')
            
            # 1. XỬ LÝ HEADER (sales_orders)
            cursor.execute("SELECT 1 FROM sales_orders WHERE so_number = ?", (so_number,))
            if not cursor.fetchone():
                # Chưa có -> Tạo mới
                cursor.execute("""
                    INSERT INTO sales_orders (so_number, customer_name, order_date, created_at, status)
                    VALUES (?, ?, ?, ?, 'Processing')
                """, (so_number, cust_name, now, now))
            else:
                # Đã có -> Cập nhật trạng thái sang Processing
                cursor.execute("UPDATE sales_orders SET status = 'Processing' WHERE so_number = ?", (so_number,))

            # 2. XỬ LÝ DETAIL (so_details)
            # Kiểm tra dòng này đã có chưa (ưu tiên theo material code)
            check_sql = "SELECT id FROM so_details WHERE so_number = ? AND material_code = ?"
            cursor.execute(check_sql, (so_number, material_code))
            
            row_tdc_id = meta.get('tdc_id')
            if row_tdc_id == '': row_tdc_id = None

            if not cursor.fetchone():
                # Chưa có Detail -> Insert
                cursor.execute("""
                    INSERT INTO so_details (
                        so_number, material_code, description, grade, 
                        thickness, width, total_weight, tdc_id  
                    )
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?)             
                """, (
                    so_number,
                    material_code,
                    f"{meta.get('grade')} {meta.get('thick')}x{meta.get('width')}",
                    meta.get('grade', ''),
                    float(meta.get('thick', 0)),
                    float(meta.get('width', 0)),
                    float(meta.get('req_weight', 0)),
                    row_tdc_id 
                ))
            else:
                # Đã có Detail -> Update lại TDC ID (phòng trường hợp người dùng đổi TDC phút cuối)
                cursor.execute("""
                    UPDATE so_details SET tdc_id = ? 
                    WHERE so_number = ? AND material_code = ?
                """, (row_tdc_id, so_number, material_code))

        # --- GIAI ĐOẠN 2: CẬP NHẬT KHO (coil_data) ---
        success_count = 0
        allocated_so_set = set()

        for item in alloc_list:
            so = str(item['so_number']).strip()
            cid = item['coil_id']
            user_note = item.get('note', '')
            p_penalty = item.get('penalty', 0)
            p_pct = item.get('match_pct', 0)
            p_ratio = item.get('match_ratio', '')
            p_msg = item.get('failed_msg', '')
            allocated_so_set.add(so)

            # Tìm thông tin để update vào cuộn
            found_meta = next((m for m in so_meta_list if str(m['so_number']) == so), {})
            cust_name_alloc = found_meta.get('customer_name', '')
            mat_code = found_meta.get('material', '')

            # Fallback tên khách
            if not cust_name_alloc:
                cursor.execute("SELECT customer_name FROM sales_orders WHERE so_number = ?", (so,))
                res = cursor.fetchone()
                cust_name_alloc = res[0] if res else "Unknown"

            # 1. Update Coil Data
            update_sql = """
                UPDATE coil_data 
                SET allocated_to = ?, allocated_order = ?, allocated_material = ?, 
                    allocated_at = ?, alloc_note = ?,
                    alloc_penalty = ?, alloc_match_pct = ?, alloc_match_ratio = ?, alloc_failed_msg = ?
                WHERE coil_id = ? AND (allocated_to IS NULL OR allocated_to = '')
            """
            cursor.execute(update_sql, (
                cust_name_alloc, so, mat_code, now, user_note, 
                p_penalty, p_pct, p_ratio, p_msg, 
                cid
            ))
            
            if cursor.rowcount > 0:
                success_count += 1
                
                # 2. [MỚI] GHI LOG CHI TIẾT NGAY TẠI ĐÂY
                # Lưu chi tiết: Ai đã gán cuộn nào vào SO nào
                log_desc = f"Gán cuộn {cid} ({cust_name_alloc}) cho đơn {so}. Ghi chú: {user_note}"
                
                cursor.execute("""
                    INSERT INTO action_history (action_type, ref_id, description, user_name, created_at)
                    VALUES (?, ?, ?, ?, ?)
                """, ('ALLOCATE_ITEM', so, log_desc, current_user, now))
        
        conn.commit()
        return jsonify({
            'status': 'success', 
            'msg': f'Thành công! Đã gán {success_count} cuộn vào {len(allocated_so_set)} đơn hàng.'
        })

    except Exception as e:
        if conn: conn.rollback()
        print(f"ROLLBACK: {str(e)}")
        return jsonify({'status': 'error', 'msg': str(e)})
    finally:
        if conn: conn.close()
# [Thêm vào alloc_run.py]

# 1. API Lấy danh sách Backlog (Đơn hàng đang chờ xử lý)
@alloc_run_bp.route('/api/get_backlog', methods=['GET'])
def get_backlog():
    try:
        conn = db.get_connection()
        
        # [CẬP NHẬT] Thêm sub-query để tính tổng khối lượng thực tế (allocated_actual)
        # ISNULL(SUM(...), 0) để đảm bảo trả về 0 nếu chưa có cuộn nào
        query = """
        SELECT 
            d.*, 
            s.customer_name,
            m.tdc_code,
            v.version_no,  -- Lấy số phiên bản đang active
            v.status as v_status,
            (SELECT ISNULL(SUM(weight), 0) FROM coil_data c 
            WHERE c.allocated_order = d.so_number AND c.allocated_material = d.material_code) as allocated_actual
        FROM so_details d
        LEFT JOIN sales_orders s ON d.so_number = s.so_number
        LEFT JOIN tdc_master m ON d.tdc_id = m.id
        -- Join để tìm version đang Active của TDC đó
        LEFT JOIN tdc_versions v ON m.id = v.master_id AND v.status = 'Active'
        WHERE s.status != 'Done' OR s.status IS NULL
        ORDER BY d.id DESC
        """
        cursor = conn.cursor()
        cursor.execute(query)
        rows = db.fetchall_as_dict(cursor)
        conn.close()
        return jsonify({'status': 'success', 'data': rows})
    except Exception as e:
        return jsonify({'status': 'error', 'msg': str(e)})

# 2. API Lưu/Cập nhật Item vào Backlog (Auto-save)
@alloc_run_bp.route('/api/save_backlog_item', methods=['POST'])
def save_backlog_item():
    try:
        req = request.json
        so = req.get('so_number')
        mat = req.get('material_code')
        desc = req.get('description', '')
        # Các thông số cần lưu
        cust = req.get('customer_name')
        grade = req.get('grade')
        thick = float(req.get('thick', 0))
        width = float(req.get('width', 0))
        weight = float(req.get('req_weight', 0))
        min_w = float(req.get('min_weight', 0))
        max_w = float(req.get('max_weight', 0))
        tdc_id = req.get('tdc_id')
        if not tdc_id or tdc_id == "": tdc_id = None

        conn = db.get_connection()
        cursor = conn.cursor()

        # B1: Đảm bảo Header (sales_orders) tồn tại
        cursor.execute("SELECT 1 FROM sales_orders WHERE so_number = ?", (so,))
        if not cursor.fetchone():
            import datetime
            now = datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")
            cursor.execute("INSERT INTO sales_orders (so_number, customer_name, created_at, status) VALUES (?, ?, ?, 'Pending')", (so, cust, now))

        # B2: Kiểm tra xem dòng Detail này đã có chưa (Check theo SO + Material)
        cursor.execute("SELECT id FROM so_details WHERE so_number = ? AND material_code = ?", (so, mat))
        row = cursor.fetchone()

        item_id = None
        if row:
            # [SỬA LỖI 1] Truy cập bằng index 0 thay vì key string 'id'
            item_id = row[0] 
            
            # UPDATE: Nếu đã có thì cập nhật lại Min/Max/Weight/TDC
            cursor.execute("""
                UPDATE so_details 
                SET total_weight = ?, min_weight = ?, max_weight = ?, tdc_id = ?, thickness = ?, width = ?, grade = ?
                WHERE id = ?
            """, (weight, min_w, max_w, tdc_id, thick, width, grade, item_id))
        else:
            # INSERT: Nếu chưa có thì thêm mới
            cursor.execute("""
                INSERT INTO so_details (so_number, material_code, description, grade, thickness, width, total_weight, min_weight, max_weight, tdc_id)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """, (so, mat, desc, grade, thick, width, weight, min_w, max_w, tdc_id))
            
            # Lấy ID vừa tạo
            try:
                item_id = cursor.lastrowid 
            except: pass

            # Với SQL Server nếu lastrowid lỗi thì query lại
            if not item_id:
                cursor.execute("SELECT TOP 1 id FROM so_details WHERE so_number=? AND material_code=? ORDER BY id DESC", (so, mat))
                new_row = cursor.fetchone()
                # [SỬA LỖI 2] Truy cập bằng index 0
                if new_row:
                    item_id = new_row[0]

        conn.commit()
        conn.close()
        return jsonify({'status': 'success', 'id': item_id, 'msg': 'Đã lưu'})
    except Exception as e:
        return jsonify({'status': 'error', 'msg': str(e)})

# 3. API Xóa khỏi Backlog (Nút X)
@alloc_run_bp.route('/api/remove_backlog_item', methods=['POST'])
def remove_backlog_item():
    try:
        req = request.json
        # Xóa dựa trên ID dòng (Unique) hoặc SO+Material
        item_id = req.get('id')
        
        conn = db.get_connection()
        if item_id:
            conn.execute("DELETE FROM so_details WHERE id = ?", (item_id,))
        else:
            # Fallback nếu không có ID
            conn.execute("DELETE FROM so_details WHERE so_number = ? AND material_code = ?", 
                         (req.get('so'), req.get('material')))
        conn.commit()
        conn.close()
        return jsonify({'status': 'success', 'msg': 'Đã xóa'})
    except Exception as e:
        return jsonify({'status': 'error', 'msg': str(e)})
# [Thêm vào alloc_run.py]

@alloc_run_bp.route('/api/check_item_status', methods=['POST'])
def check_item_status():
    try:
        req = request.json
        so = req.get('so_number')
        mat = req.get('material_code')
        
        if not so or not mat: 
            return jsonify({'status': 'error', 'msg': 'Thiếu thông tin'})

        conn = db.get_connection()
        cursor = conn.cursor()

        # 1. Kiểm tra trong Backlog (Bảng so_details)
        # Xem người dùng đã từng thêm dòng này vào danh sách chờ chưa
        cursor.execute("""
            SELECT SUM(total_weight) 
            FROM so_details 
            WHERE so_number = ? AND material_code = ?
        """, (so, mat))
        row_backlog = cursor.fetchone()
        backlog_weight = row_backlog[0] if row_backlog and row_backlog[0] else 0

        # 2. Kiểm tra đã phân bổ xong (Bảng coil_data)
        # Xem thực tế đã gán được bao nhiêu tấn cho dòng này
        cursor.execute("""
            SELECT SUM(weight) 
            FROM coil_data 
            WHERE allocated_order = ? AND allocated_material = ?
        """, (so, mat))
        row_alloc = cursor.fetchone()
        allocated_weight = row_alloc[0] if row_alloc and row_alloc[0] else 0

        conn.close()
        
        return jsonify({
            'status': 'success',
            'backlog_weight': backlog_weight,
            'allocated_weight': allocated_weight
        })

    except Exception as e:
        return jsonify({'status': 'error', 'msg': str(e)})


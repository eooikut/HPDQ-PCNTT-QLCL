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
        if not req_items: return jsonify({'status':'error', 'msg':'Chưa có dữ liệu đầu vào!'})
        conn = db.get_connection()
        cursor = conn.cursor()
        cursor.execute("SELECT * FROM tdc_master")
        all_tdcs = db.fetchall_as_dict(cursor)

        tdc_map = {row['id']: dict(row) for row in all_tdcs}
        cursor = conn.cursor()
        cursor.execute("SELECT coil_id, scores, grade, weight, target_thick, target_width FROM coil_data WITH (NOLOCK) WHERE (allocated_to IS NULL OR allocated_to = '')")
        inventory_rows = db.fetchall_as_dict(cursor)
        conn.close()
        inventory = []
        for r in inventory_rows:
            item = dict(r)
            item['scores'] = json.loads(item['scores']) if item['scores'] else {}
            item['grade'] = str(item['grade']).strip().upper()
            
            # [QUAN TRỌNG] Ép kiểu Weight về số thực, nếu Null thì coi là 0
            item['weight'] = float(item['weight']) if item['weight'] is not None else 0.0
            
            # [QUAN TRỌNG] Ép kiểu Dày/Rộng luôn cho chắc
            item['thick'] = float(item['target_thick']) if item['target_thick'] else 0.0
            item['width'] = float(item['target_width']) if item['target_width'] else 0.0
            
            inventory.append(item)

        final_results = []
        used_coil_ids = set()

        for req in req_items:
            try:
                # --- [UPDATE 1] LẤY THÊM THAM SỐ MIN/MAX ---
                so_number = req.get('so_number', 'N/A')
                tdc_id = int(req.get('tdc_id', 0))
                req_thick = float(req.get('thick', 0))
                req_width = float(req.get('width', 0))
                req_weight_target = float(req.get('req_weight', 0))
                
                # Lấy giới hạn min/max (Mặc định là 0 nếu không nhập)
                req_min_w = float(req.get('min_weight', 0))
                req_max_w = float(req.get('max_weight', 0))

                tdc_info = tdc_map.get(tdc_id)
                if not tdc_info: continue
                
                target_grade = tdc_info['grade']
                criteria_list = json.loads(tdc_info['criteria_json']) if tdc_info['criteria_json'] else []
                cust_name = tdc_info['customer_name']

                candidates = []
                current_weight_sum = 0

                for coil in inventory:
                    if coil['coil_id'] in used_coil_ids: continue
                    if coil['grade'] != target_grade: continue

                    # [LỌC CỨNG] Kích thước
                    if abs(coil['thick'] - req_thick) > 0.0: continue 
                    if abs(coil['width'] - req_width) > 0.0: continue

                    # --- [UPDATE 2] LỌC CỨNG MIN/MAX WEIGHT ---
                    # Nếu yêu cầu Min > 0 mà cuộn nhẹ hơn -> Bỏ
                    if req_min_w > 0 and coil['weight'] < req_min_w: continue
                    # Nếu yêu cầu Max > 0 mà cuộn nặng hơn -> Bỏ
                    if req_max_w > 0 and coil['weight'] > req_max_w: continue

                    # ... (Đoạn tính điểm Penalty giữ nguyên) ...
                    total_penalty = 0
                    failed_reasons = [] 
                    match_type = 'PERFECT'
                    sort_diffs = [] # Danh sách các khoảng cách để so sánh chi tiết
                    scores = coil['scores']
                    
                    for crit in criteria_list:
                        defect = crit['defect']
                        
                        # Target: Là điểm "Mơ ước" (Ví dụ C6 là tốt nhất thì set Target=6)
                        target = crit.get('target', 1) 
                        val = scores.get(defect, 1) # Nếu thiếu data coi như là 1 (hoặc 0 tùy bạn)
                        allowed_range = crit.get('range', [])

                        diff_from_target = abs(val - target)

                        if val == 0:
                            # Xử lý thiếu dữ liệu (Giữ nguyên)
                            total_penalty += 20 
                            failed_reasons.append(f"{defect}:Missing(C0)")
                            match_type = 'PROP_MISMATCH'
                            sort_diffs.append(99) 
                            continue
                        
                        if val not in allowed_range:
                            dist_error = abs(val - target) # Khoảng cách lỗi
                            if dist_error == 1: penalty = 20; reason = f"{defect}:C{val}"
                            elif dist_error == 2: penalty = 50; reason = f"{defect}:C{val} (Lệch 2)"
                            else: penalty = 999; reason = "FAIL"
                            
                            total_penalty += penalty
                            if penalty < 999:
                                match_type = 'PROP_MISMATCH'
                                failed_reasons.append(reason)
                        sort_diffs.append(diff_from_target)

                    if total_penalty < 800:
                        c_item = coil.copy()
                        c_item.update({
                            'penalty': total_penalty,
                            'sort_keys': tuple(sort_diffs),
                            'match_type': match_type,
                            'failed_msg': ', '.join(failed_reasons),
                            'customer_alloc': cust_name,
                            'so_number': so_number,
                            'req_desc': f"{req_thick} x {req_width}"
                        })
                        candidates.append(c_item)

                # Sắp xếp và Cắt theo Tổng khối lượng yêu cầu
                candidates.sort(key=lambda x: (x['penalty'], x['sort_keys']))

                for cand in candidates:
                    final_results.append(cand) # Sửa lại logic add thẳng vào final list
                    current_weight_sum += cand['weight']
                    used_coil_ids.add(cand['coil_id'])
                    
                    # Đủ khối lượng thì dừng tìm cho dòng này
                    if current_weight_sum >= req_weight_target:
                        break
            
            except Exception as ex: 
                print(f"❌ LỖI DÒNG REQUEST: {ex}")
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
            user_note = item.get('note', '') # Lấy ghi chú nếu có
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
                    allocated_at = ?, alloc_note = ?
                WHERE coil_id = ? AND (allocated_to IS NULL OR allocated_to = '')
            """
            cursor.execute(update_sql, (cust_name_alloc, so, mat_code, now, user_note, cid))
            
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
            d.id, d.so_number, d.material_code, d.grade, 
            d.thickness, d.width, d.total_weight, 
            d.min_weight, d.max_weight, d.tdc_id,
            s.customer_name,
            (
                SELECT ISNULL(SUM(weight), 0) 
                FROM coil_data c 
                WHERE c.allocated_order = d.so_number 
                  AND c.allocated_material = d.material_code
            ) as allocated_actual
        FROM so_details d
        LEFT JOIN sales_orders s ON d.so_number = s.so_number
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
                INSERT INTO so_details (so_number, material_code, customer_name, grade, thickness, width, total_weight, min_weight, max_weight, tdc_id)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """, (so, mat, cust, grade, thick, width, weight, min_w, max_w, tdc_id))
            
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


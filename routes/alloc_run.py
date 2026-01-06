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
                    sort_diffs = []
                    scores = coil['scores']
                    
                    for crit in criteria_list:
                        defect = crit['defect']
                        target = crit.get('target', 1) 
                        val = scores.get(defect, 1)
                        allowed_range = crit.get('range', [])
                        if val == 0:
                            # Nếu thiếu dữ liệu: Phạt nhẹ (20 điểm) và BỎ QUA tính toán khoảng cách
                            total_penalty += 20 
                            failed_reasons.append(f"{defect}:Missing(C0)")
                            match_type = 'PROP_MISMATCH' # Đánh dấu là không khớp hoàn hảo
                            continue
                        dist = 0
                        if val not in allowed_range:
                            dist = abs(val - target)
                            if dist == 1: penalty = 20; reason = f"{defect}:C{val}"
                            elif dist == 2: penalty = 50; reason = f"{defect}:C{val} (Lệch 2)"
                            else: penalty = 999; reason = "FAIL"
                            total_penalty += penalty
                            if penalty < 999:
                                match_type = 'PROP_MISMATCH'
                                failed_reasons.append(reason)
                        sort_diffs.append(dist)

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
        tdc_id = req.get('tdc_id')
        alloc_list = req.get('allocations', []) # List [{coil_id, so_number, ...}]

        if not alloc_list:
            return jsonify({'status': 'error', 'msg': 'Danh sách phân bổ trống!'})

        conn = db.get_connection()
        cursor = conn.cursor()
        
        import datetime
        now = datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")

        # --- BƯỚC 1: Lấy thông tin header ---
        # Lấy tên khách từ TDC để lưu lịch sử
        cursor.execute("SELECT customer_name FROM tdc_master WHERE id=?", (tdc_id,))
        row = cursor.fetchone()
        cust_name = row['customer_name'] if row else "Unknown"

        # --- BƯỚC 2: Xử lý danh sách SO (Header) ---
        unique_sos = set(item['so_number'] for item in alloc_list if item['so_number'] != 'N/A')
        
        # Lưu ý: Tùy vào DB (SQLite hay SQL Server) mà cú pháp BEGIN TRANSACTION có thể khác nhau. 
        # Python DB-API thường tự động start transaction khi có lệnh ghi, ta chỉ cần commit/rollback.
        
        for so in unique_sos:
            # Tạo đơn hàng nếu chưa tồn tại
            # Sử dụng cú pháp tương thích SQL Server/SQLite
            check_sql = "SELECT 1 FROM customer_orders WHERE so_number = ?"
            cursor.execute(check_sql, (so,))
            if not cursor.fetchone():
                cursor.execute("""
                    INSERT INTO customer_orders (so_number, customer_name, tdc_id, created_at)
                    VALUES (?, ?, ?, ?)
                """, (so, cust_name, tdc_id, now))

        # --- BƯỚC 3: Cập nhật từng cuộn (Có kiểm tra tranh chấp) ---
        success_count = 0
        
        for item in alloc_list:
            so = item['so_number']
            cid = item['coil_id']
            
            # [QUAN TRỌNG] Chỉ update nếu cuộn đó đang trống (NULL hoặc rỗng)
            # Điều này ngăn chặn 2 người cùng allocation 1 cuộn
            update_sql = """
                UPDATE coil_data 
                SET allocated_to = ?, allocated_order = ?, allocated_at = ? 
                WHERE coil_id = ? AND (allocated_to IS NULL OR allocated_to = '')
            """
            cursor.execute(update_sql, (cust_name, so, now, cid))
            
            # Kiểm tra xem có dòng nào thực sự được update không
            if cursor.rowcount == 0:
                # Nếu rowcount = 0 nghĩa là:
                # 1. Cuộn không tồn tại
                # 2. HOẶC Cuộn đã bị người khác lấy mất (allocated_to không null)
                raise Exception(f"Lỗi: Cuộn {cid} đã bị thay đổi trạng thái hoặc được phân bổ bởi người khác!")
            
            success_count += 1
        
        # --- BƯỚC 4: Chốt giao dịch ---
        conn.commit() # Chỉ lưu khi TẤT CẢ các lệnh trên đều thành công
        return jsonify({
            'status': 'success', 
            'msg': f'Thành công! Đã phân bổ {success_count} cuộn vào {len(unique_sos)} đơn hàng.'
        })

    except Exception as e:
        # Nếu có bất kỳ lỗi nào (kể cả lỗi cuộn đã bị lấy), hoàn tác toàn bộ
        if conn: conn.rollback()
        print(f"ROLLBACK TRANSACTION: {str(e)}")
        return jsonify({'status': 'error', 'msg': str(e)})
        
    finally:
        if conn: conn.close()
# --- API CHỐT ĐƠN HÀNG (MỚI: Lưu vào 3 bảng) ---
@alloc_run_bp.route('/api/confirm_allocation_v2', methods=['POST'])
def confirm_allocation_v2():
    try:
        req = request.json
        so_number = req.get('so_number')
        tdc_id = req.get('tdc_id')
        items = req.get('items', [])     # List quy cách
        coil_ids = req.get('coil_ids', []) # List ID cuộn được chọn

        if not so_number: return jsonify({'status':'error', 'msg':'Thiếu số SO!'})

        # 1. Lưu Header & Detail vào DB (Lịch sử đơn hàng)
        success, msg = db.save_sales_order(so_number, tdc_id, items)
        if not success: return jsonify({'status':'error', 'msg': msg})

        # 2. Update trạng thái cuộn trong kho
        conn = db.get_connection()
        import datetime
        now = datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        
        # Cần lấy tên khách hàng từ TDC ID để lưu vào field allocated_to (cho tương thích code cũ)
        tdc = conn.execute("SELECT customer_name FROM tdc_master WHERE id=?", (tdc_id,)).fetchone()
        cust_name = tdc['customer_name'] if tdc else "Unknown"

        for cid in coil_ids:
            conn.execute("""
                UPDATE coil_data 
                SET allocated_to = ?, allocated_order = ?, allocated_at = ? 
                WHERE coil_id = ?
            """, (cust_name, so_number, now, cid))
        
        conn.commit()
        conn.close()
        return jsonify({'status': 'success', 'msg': 'Đã tạo đơn hàng và giữ cuộn thành công!'})

    except Exception as e:
        return jsonify({'status': 'error', 'msg': str(e)})


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
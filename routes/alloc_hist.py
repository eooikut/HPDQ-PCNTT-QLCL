from flask import Blueprint, render_template, request, jsonify
import json
import db  # Module db.py

alloc_hist_bp = Blueprint('alloc_hist_bp', __name__)

@alloc_hist_bp.route('/allocation_history', methods=['GET'])
def allocation_history_page():
    return render_template('allocation_history.html')

# [Trong file alloc_hist.py]

@alloc_hist_bp.route('/api/get_history_summary', methods=['GET'])
def get_history_summary():
    try:
        conn = db.get_connection()
        cursor = conn.cursor()

        # BƯỚC 1: Lấy thông tin TDC Master để chấm điểm
        cursor.execute("SELECT id, criteria_json FROM tdc_master")
        tdc_rows = db.fetchall_as_dict(cursor)
        # Tạo từ điển map ID -> Criteria để tra cứu cho nhanh
        tdc_library = {}
        for row in tdc_rows:
            try:
                tdc_library[row['id']] = json.loads(row['criteria_json']) if row['criteria_json'] else []
            except:
                tdc_library[row['id']] = []

        # BƯỚC 2: Lấy HEADER + Chi tiết Đơn hàng (Thêm cột tdc_id)
        query_orders = """
            SELECT 
                so.so_number, 
                so.customer_name, 
                so.order_date,
                d.material_code, 
                d.description, 
                d.total_weight as req_weight, 
                d.thickness, 
                d.width,
                d.tdc_id  -- [MỚI] Lấy thêm TDC ID để biết đường chấm điểm
            FROM sales_orders so
            LEFT JOIN so_details d ON so.so_number = d.so_number
            ORDER BY so.created_at DESC
        """
        cursor.execute(query_orders)
        raw_rows = db.fetchall_as_dict(cursor)

        orders_map = {}
        for r in raw_rows:
            so = r['so_number']
            if so not in orders_map:
                orders_map[so] = {
                    'so_number': so,
                    'customer_name': r['customer_name'],
                    'date': r['order_date'],
                    'total_target': 0,
                    'total_actual': 0,
                    'items': []
                }
            
            if r['req_weight'] is not None:
                w = float(r['req_weight'])
                orders_map[so]['total_target'] += w
                orders_map[so]['items'].append({
                    'material': r['material_code'], 
                    'desc': r['description'],
                    'thick': float(r['thickness']) if r['thickness'] else 0,
                    'width': float(r['width']) if r['width'] else 0,
                    'tdc_id': r['tdc_id'], # Lưu TDC ID vào item
                    'req': w,
                    'actual': 0
                })

        # BƯỚC 3: Lấy THỰC TẾ (Actual) từ kho cuộn
        query_coils = """
            SELECT 
                coil_id, 
                allocated_order, 
                allocated_material, 
                weight, 
                target_thick AS thick,
                target_width AS width,
                grade, 
                scores, 
                allocated_to,
                alloc_note -- Lấy thêm ghi chú nếu cần
            FROM coil_data WITH (NOLOCK) 
            WHERE allocated_order IS NOT NULL AND allocated_order != ''
        """
        cursor.execute(query_coils)
        coils_rows = db.fetchall_as_dict(cursor)
        conn.close()

        # BƯỚC 4: Logic Mapping & TÍNH ĐIỂM (Re-scoring)
        allocated_coils = []
        for c in coils_rows:
            so = c['allocated_order']
            # Parse scores từ JSON
            coil_scores = json.loads(c['scores']) if c['scores'] else {}
            c['scores'] = coil_scores # Gán ngược lại để trả về frontend
            
            # Mặc định penalty = 0 (Chuẩn)
            c['penalty'] = 0 

            if so in orders_map:
                w = float(c['weight']) if c['weight'] else 0
                orders_map[so]['total_actual'] += w
                
                coil_mat = c.get('allocated_material', '')
                matched_item = None
                
                # Tìm xem cuộn này thuộc dòng (Item) nào của đơn hàng
                # Ưu tiên 1: Map theo Material
                if coil_mat:
                    for item in orders_map[so]['items']:
                        if item['material'] == coil_mat:
                            item['actual'] += w
                            matched_item = item
                            break
                
                # Ưu tiên 2: Fallback theo Kích thước (nếu không map được theo material)
                if not matched_item:
                    for item in orders_map[so]['items']:
                        if abs(item['thick'] - c['thick']) < 0.05 and abs(item['width'] - c['width']) < 10:
                            item['actual'] += w
                            matched_item = item
                            break
                
                # [QUAN TRỌNG] TÍNH LẠI ĐIỂM PHẠT (RE-CALCULATE PENALTY)
                if matched_item and matched_item.get('tdc_id'):
                    tdc_id = matched_item['tdc_id']
                    criteria = tdc_library.get(tdc_id, [])
                    
                    # Logic chấm điểm (Copy logic từ alloc_run.py)
                    total_penalty = 0
                    for crit in criteria:
                        defect = crit['defect']
                        target = crit.get('target', 1)
                        val = coil_scores.get(defect, 1) # Nếu thiếu data coi như 1
                        allowed_range = crit.get('range', [])
                        
                        if val == 0: # Thiếu data
                            total_penalty += 20
                        elif val not in allowed_range:
                            dist = abs(val - target)
                            if dist == 1: total_penalty += 20
                            elif dist == 2: total_penalty += 50
                            else: total_penalty += 999
                    
                    c['penalty'] = total_penalty

            allocated_coils.append(c)

        return jsonify({
            'orders': list(orders_map.values()), 
            'coils': allocated_coils
        })

    except Exception as e:
        print(f"History API Error: {str(e)}")
        return jsonify({'orders': [], 'coils': [], 'msg': str(e)})
@alloc_hist_bp.route('/api/release_coils', methods=['POST'])
def release_coils():
    conn = None
    try:
        req = request.json
        coil_ids = req.get('coil_ids', [])
        # Nếu sau này có Login, lấy user từ session. Tạm thời lấy từ request hoặc default
        current_user = req.get('user_name', 'QC_User') 
        
        if not coil_ids: 
            return jsonify({'status': 'error', 'msg': 'Chưa chọn cuộn nào'})
        
        conn = db.get_connection()
        cursor = conn.cursor()
        
        import datetime
        now = datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")

        # 1. LẤY THÔNG TIN CŨ ĐỂ GHI LOG (Quan trọng: Phải làm trước khi Update)

        placeholders = ','.join(['?'] * len(coil_ids))
        
        # Query xem những cuộn này đang thuộc SO nào
        sql_check = f"SELECT coil_id, allocated_order FROM coil_data WHERE coil_id IN ({placeholders})"
        cursor.execute(sql_check, coil_ids)
        coils_info = cursor.fetchall() # List các tuple: (coil_id, so_number)

        # 2. THỰC HIỆN GỠ BỎ (UPDATE)
        sql_update = f"""
            UPDATE coil_data 
            SET allocated_to = NULL, allocated_order = NULL, allocated_at = NULL, allocated_material = NULL, alloc_note = NULL
            WHERE coil_id IN ({placeholders})
        """
        cursor.execute(sql_update, coil_ids)
        
        # 3. GHI LOG LỊCH SỬ (AUDIT)
        for row in coils_info:
            # row[0] là coil_id, row[1] là allocated_order
            cid = row[0]
            so_num = row[1] if row[1] else 'N/A'
            
            log_desc = f"Gỡ bỏ cuộn {cid} ra khỏi đơn hàng {so_num}"
            cursor.execute("""
                INSERT INTO action_history (action_type, ref_id, description, user_name, created_at)
                VALUES (?, ?, ?, ?, ?)
            """, ('RELEASE_ITEM', str(so_num), log_desc, current_user, now))

        conn.commit()
        return jsonify({'status': 'success', 'msg': f'Đã gỡ và ghi log {len(coil_ids)} cuộn.'})

    except Exception as e:
        if conn: conn.rollback()
        print(f"Release Error: {str(e)}")
        return jsonify({'status': 'error', 'msg': str(e)})
    finally:
        if conn: conn.close()
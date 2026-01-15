from flask import Blueprint, render_template, request, jsonify
import json
import db  # Module db.py

alloc_hist_bp = Blueprint('alloc_hist_bp', __name__)

@alloc_hist_bp.route('/allocation_history', methods=['GET'])
def allocation_history_page():
    return render_template('allocation_history.html')
@alloc_hist_bp.route('/api/get_history_summary', methods=['GET'])
def get_history_summary():
    try:
        conn = db.get_connection()
        cursor = conn.cursor()

        # 1. LẤY THƯ VIỆN TDC & MAP (Giữ nguyên)
        cursor.execute("SELECT id, criteria_json FROM tdc_master")
        tdc_rows = db.fetchall_as_dict(cursor)
        tdc_library = {}
        for row in tdc_rows:
            try:
                tdc_library[row['id']] = json.loads(row['criteria_json']) if row['criteria_json'] else []
            except:
                tdc_library[row['id']] = []

        # 2. LẤY DANH SÁCH SALES ORDERS (Giữ nguyên)
        query_orders = """
            SELECT 
                so.so_number, so.customer_name, so.order_date,
                d.material_code, d.description, d.total_weight as line_req_weight, 
                d.thickness, d.width, d.tdc_id
            FROM sales_orders so
            LEFT JOIN so_details d ON so.so_number = d.so_number
            ORDER BY so.created_at DESC
        """
        cursor.execute(query_orders)
        raw_rows = db.fetchall_as_dict(cursor)

        orders_map = {}
        so_mat_to_tdc = {} 

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
            
            if r['line_req_weight']:
                w = float(r['line_req_weight'])
                orders_map[so]['total_target'] += w
                orders_map[so]['items'].append({
                    'material': r['material_code'], 
                    'desc': r['description'],
                    'thick': float(r['thickness']) if r['thickness'] else 0,
                    'width': float(r['width']) if r['width'] else 0,
                    'tdc_id': r['tdc_id'],
                    'req': w
                })
                if r['material_code']:
                    so_mat_to_tdc[(so, r['material_code'])] = r['tdc_id']

        # 3. LẤY DANH SÁCH CUỘN ĐÃ PHÂN BỔ
        # Đảm bảo query lấy đủ alloc_penalty
        query_coils = """
            SELECT 
                coil_id, allocated_order, allocated_material, weight, grade, scores, 
                allocated_to, alloc_note,
                target_thick, target_width, 
                alloc_penalty, alloc_match_pct, alloc_match_ratio, alloc_failed_msg
            FROM coil_data WITH (NOLOCK) 
            WHERE allocated_order IS NOT NULL AND allocated_order != ''
        """
        cursor.execute(query_coils)
        coils_rows = db.fetchall_as_dict(cursor)
        conn.close()

        # 4. XỬ LÝ DỮ LIỆU
        allocated_coils = []
        for c in coils_rows:
            c['thick'] = float(c['target_thick']) if c['target_thick'] else 0
            c['width'] = float(c['target_width']) if c['target_width'] else 0
            c['weight'] = float(c['weight']) if c['weight'] else 0
            
            # --- [QUAN TRỌNG] LẤY TRỰC TIẾP TỪ DB, KHÔNG TÍNH LẠI ---
            c['penalty'] = c['alloc_penalty'] if c['alloc_penalty'] is not None else 0
            c['match_pct'] = c['alloc_match_pct'] if c['alloc_match_pct'] is not None else 0
            
            scores = {}
            if c['scores']:
                try: scores = json.loads(c['scores'])
                except: pass
            
            # --- TÍNH SORT TUPLE (Chỉ dùng để sort, ko gán lại penalty) ---
            key = (c['allocated_order'], c['allocated_material'])
            tdc_id = so_mat_to_tdc.get(key)
            sort_diffs = [] 
            
            if tdc_id and tdc_id in tdc_library:
                criteria_list = tdc_library[tdc_id]
                for crit in criteria_list:
                    defect = crit['defect']
                    val = scores.get(defect, 0)
                    target = crit.get('target', 1)
                    allowed_range = crit.get('range', [])
                    
                    if val == 0:
                        sort_diffs.append(99) # Missing -> Đẩy xuống
                    elif val in allowed_range:
                        sort_diffs.append(0)  # Pass
                    else:
                        sort_diffs.append(abs(val - target)) # Fail
            
            c['_sort_priority'] = tuple(sort_diffs)

            # Xử lý hiển thị Ratio
            if c['alloc_match_ratio']: c['match_ratio'] = c['alloc_match_ratio']
            else: c['match_ratio'] = "Old"
            
            # Đảm bảo failed_msg không bị None
            c['alloc_failed_msg'] = c['alloc_failed_msg'] if c['alloc_failed_msg'] else ''

            allocated_coils.append(c)
            
            # Cộng tổng
            so_num = c['allocated_order']
            if so_num in orders_map:
                orders_map[so_num]['total_actual'] += c['weight']

        # 5. SORT GIỮ NGUYÊN
        allocated_coils.sort(key=lambda x: (
            0 if x['penalty'] == 0 else 1,   
            x['penalty'],                    
            x['_sort_priority'],             
            -x['match_pct']                  
        ))

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
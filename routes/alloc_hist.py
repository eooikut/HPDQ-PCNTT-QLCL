from flask import Blueprint, render_template, request, jsonify, session
import json
import db
import datetime
from excel_processor import normalize_usage_purpose
from auth.decorator import login_required, permission_required
alloc_hist_bp = Blueprint('alloc_hist_bp', __name__)

@alloc_hist_bp.route('/allocation_history', methods=['GET'])
@permission_required('allocation_history')
def allocation_history_page():
    return render_template('allocation_history.html')

@alloc_hist_bp.route('/api/get_history_summary', methods=['GET'])
@permission_required('allocation_history')
def get_history_summary():
    conn = None
    try:
        conn = db.get_connection()
        cursor = conn.cursor()
        target_so = request.args.get('so_number')
        target_mat = request.args.get('material_code')
        # 1. LẤY DANH SÁCH VERSION TDC VÀ TẠO TỪ ĐIỂN DỊCH ID
        query_versions = """
            SELECT v.id, v.criteria_json, v.version_no, v.status, m.tdc_code, m.id as master_id 
            FROM tdc_versions v
            LEFT JOIN tdc_master m ON v.master_id = m.id
        """
        cursor.execute(query_versions)
        v_rows = db.fetchall_as_dict(cursor)
        
        version_library = {}
        master_to_active_version = {} # [MỚI] Dịch ID
        
        for row in v_rows:
            criteria = []
            try: criteria = json.loads(row['criteria_json']) if row['criteria_json'] else []
            except: pass
            
            version_library[row['id']] = {
                'criteria': criteria, 'code': row['tdc_code'] or 'N/A', 'ver_no': row['version_no']
            }
            if row['status'] == 'Active':
                master_to_active_version[row['master_id']] = row['id']

        # 2. LẤY DANH SÁCH ĐƠN HÀNG ĐÃ SETUP (KÈM USAGE_PURPOSE)
        query_orders = """
            SELECT 
                so.so_number, so.customer_name, so.order_date,
                d.material_code, d.description, d.total_weight as line_req_weight, 
                d.thickness, d.width, d.tdc_id, d.usage_purpose
            FROM sales_orders so
            LEFT JOIN so_details d ON so.so_number = d.so_number
            ORDER BY so.created_at DESC
        """
        cursor.execute(query_orders)
        raw_rows = db.fetchall_as_dict(cursor)

        orders_map = {}
        so_tdc_map = {} 
        so_purpose_map = {} # [MỚI] Lưu mục đích sử dụng của SO để Auto-Discovery dùng
        
        for r in raw_rows:
            raw_so = r['so_number']
            if raw_so is None: continue
            
            so_val = str(raw_so).strip()
            mat_val = str(r['material_code']).strip() if r['material_code'] else 'N/A'
            unique_key = f"{so_val}__{mat_val}"
            
            if r['tdc_id']: so_tdc_map[unique_key] = r['tdc_id']
            if r['usage_purpose']: so_purpose_map[so_val] = normalize_usage_purpose(r['usage_purpose'])
            
            if unique_key not in orders_map:
                orders_map[unique_key] = {
                    'unique_key': unique_key, 'so_number': so_val, 'material_code': mat_val,
                    'customer_name': r['customer_name'], 'date': r['order_date'],
                    'total_target': 0, 'total_actual': 0, 
                    'desc_meta': f"{float(r['thickness'] or 0)} x {float(r['width'] or 0)}" 
                }
            if r['line_req_weight']: orders_map[unique_key]['total_target'] += float(r['line_req_weight'])

        # 3. CHUẨN BỊ DATA CHO SMART AUTO-DISCOVERY KIỀNG 3 CHÂN
        cursor.execute("SELECT [Sales Document] as so_number, MAX([Customer]) as customer_name FROM [factory].[dbo].[so] WITH(NOLOCK) GROUP BY [Sales Document]")
        sap_customer_map = {str(r['so_number']).strip(): str(r['customer_name']).strip() for r in db.fetchall_as_dict(cursor)}

        cursor.execute("""
            SELECT m.id as tdc_id, m.customer_name, m.grade, m.usage_purpose 
            FROM tdc_master m JOIN tdc_versions v ON m.id = v.master_id WHERE v.status = 'Active'
        """)
        tdc_lookup_dict = {}
        for r in db.fetchall_as_dict(cursor):
            purp = normalize_usage_purpose(r['usage_purpose'])
            key = f"{str(r['customer_name']).strip().lower()}_{str(r['grade']).strip().lower()}_{purp}"
            if key not in tdc_lookup_dict: tdc_lookup_dict[key] = []
            tdc_lookup_dict[key].append(r['tdc_id'])

        # 4. LẤY DANH SÁCH CUỘN ĐÃ PHÂN BỔ TỪ COIL_DATA
        if not target_so:
            query_agg = """
                SELECT 
                    COALESCE(NULLIF(allocated_order, ''), sap_so_mapping) as final_so,
                    COALESCE(NULLIF(allocated_material, ''), sap_material) as final_mat,
                    SUM(weight) as total_weight
                FROM coil_data WITH (NOLOCK)
                WHERE (allocated_order IS NOT NULL AND allocated_order <> '') 
                   OR (sap_so_mapping IS NOT NULL AND sap_so_mapping <> '' AND sap_so_mapping <> '0')
                GROUP BY 
                    COALESCE(NULLIF(allocated_order, ''), sap_so_mapping),
                    COALESCE(NULLIF(allocated_material, ''), sap_material)
            """
            cursor.execute(query_agg)
            for row in db.fetchall_as_dict(cursor):
                f_so = str(row['final_so']).strip()
                f_mat = str(row['final_mat']).strip() if row['final_mat'] else 'N/A'
                t_key = f"{f_so}__{f_mat}"
                if t_key in orders_map:
                    orders_map[t_key]['total_actual'] += float(row['total_weight'] or 0)
            
            # Trả về luôn, không chạy xuống phần tính điểm cuộn
            return jsonify({
                'orders': list(orders_map.values()), 
                'version_lib': version_library 
            })
        else:
            query_coils = """
                SELECT 
                    coil_id, ID_XuLy, allocated_order, allocated_material, weight, grade, scores, 
                    allocated_to, alloc_note, allocated_tdc_id, 
                    target_thick, target_width, 
                    alloc_penalty, alloc_match_pct, alloc_match_ratio, alloc_failed_msg,
                    sap_so_mapping, sap_material, sap_status, quality_level, production_date
                FROM coil_data WITH (NOLOCK) 
                WHERE (allocated_order = ? AND allocated_material = ?) 
                   OR (sap_so_mapping = ? AND sap_material = ?)
            """
            cursor.execute(query_coils, (target_so, target_mat, target_so, target_mat))
            coils_rows = db.fetchall_as_dict(cursor)

        # 5. KHỚP DỮ LIỆU VÀ AUTO-EVALUATE
        allocated_coils = []
        coils_to_update_db = []
        details_to_insert_db = []
        now_str = datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        
        for c in coils_rows:
            c['ID_XuLy'] = str(c.get('ID_XuLy') or '').strip()
            c['thick'] = float(c['target_thick']) if c['target_thick'] else 0
            c['width'] = float(c['target_width']) if c['target_width'] else 0
            c['weight'] = float(c['weight']) if c['weight'] else 0
            
            raw_alloc_order = c['allocated_order']
            raw_alloc_mat = c['allocated_material']
            sap_so = str(c.get('sap_so_mapping') or '').strip()
            sap_mat = str(c.get('sap_material') or '').strip()
            
            # --- [MỚI] LOGIC GỘP SO HIỂN THỊ ---
            # Ưu tiên kế hoạch của Web. Nếu Web trống (cuộn mới hoàn toàn do SAP đẩy về), thì lấy thông tin của SAP để hiển thị
            is_pure_sap = False
            if raw_alloc_order and str(raw_alloc_order).strip():
                display_so = str(raw_alloc_order).strip()
                display_mat = str(raw_alloc_mat).strip() if raw_alloc_mat else 'N/A'
            else:
                display_so = sap_so
                display_mat = sap_mat if sap_mat else 'N/A'
                is_pure_sap = True

            if not display_so or display_so == 'None' or display_so == '0':
                continue

            target_key = f"{display_so}__{display_mat}"
            
            # --- LOGIC ĐỐI CHIẾU XUNG ĐỘT ---
            c['conflict_status'] = 'OK'
            c['sap_actual_so'] = sap_so

            if not is_pure_sap:
                # Cuộn do Web chỉ định
                if sap_so and sap_so != 'None' and sap_so != '0' and sap_so != display_so:
                    c['conflict_status'] = 'STOLEN' # Bị cướp
                elif not sap_so or sap_so == 'None' or sap_so == '0':
                    c['conflict_status'] = 'PENDING_SAP' # Đang đợi SAP đồng bộ
            else:
                # Cuộn do SAP tự đẩy về (Web chưa làm gì cả)
                c['conflict_status'] = 'SAP_AUTO'

            # Gán lại giá trị để HTML và Auto-discovery bên dưới dùng chung
            c['allocated_order'] = display_so 
            c['allocated_material'] = display_mat
            
            if target_key in orders_map:
                orders_map[target_key]['total_actual'] += c['weight']
           

            scores = {}
            if c['scores']:
                try: scores = json.loads(c['scores'])
                except: pass
            c['scores'] = scores 
            c['allocated_material'] = display_mat
            c['alloc_failed_msg'] = c['alloc_failed_msg'] if c['alloc_failed_msg'] else ''
            
            used_version_id = c['allocated_tdc_id']
            
            # --- LOGIC AUTO-DISCOVERY & TÍNH ĐIỂM ---
            
            # [BƯỚC 1]: Kéo logic tìm TDC ra ngoài để LÚC NÀO CŨNG TÌM xem TDC kỳ vọng hiện tại là gì
            found_master_id = so_tdc_map.get(target_key) 
            
            if not found_master_id: 
                # Ưu tiên 2: Tự động nội suy theo Khách + Mác + Mục đích SD (Kiềng 3 chân)
                cust_name = sap_customer_map.get(display_so)
                coil_grade = c['grade']
                excel_purpose = so_purpose_map.get(display_so, 'unknown') # Lấy mục đích do ETL nhét vào
                
                if cust_name and coil_grade:
                    lookup_key = f"{cust_name.lower()}_{str(coil_grade).strip().lower()}_{excel_purpose}"
                    possible_tdcs = tdc_lookup_dict.get(lookup_key, [])
                    
                    if len(possible_tdcs) == 1: 
                        found_master_id = possible_tdcs[0]
                        if target_key not in [f"{x[0]}__{x[1]}" for x in details_to_insert_db]:
                            details_to_insert_db.append((display_so, display_mat, cust_name, coil_grade, c['thick'], c['width'], found_master_id))
            
            # Dịch Master ID -> Version ID đang Active
            expected_version_id = master_to_active_version.get(found_master_id)
            if not expected_version_id and used_version_id:
                expected_version_id = used_version_id
            # [BƯỚC 2]: QUYẾT ĐỊNH CÓ CẦN TÍNH LẠI HAY KHÔNG
            # Chỉ tính lại khi: Chưa có TDC HOẶC (Là cuộn do SAP tự map VÀ TDC kỳ vọng đã bị đổi)
            need_recalc = (used_version_id is None) or (is_pure_sap and expected_version_id is not None and expected_version_id != used_version_id)

            # [BƯỚC 2]: LUÔN TÍNH TOÁN DỰA TRÊN SCORES HIỆN TẠI VÀ SO SÁNH VỚI DB (AUTO-HEAL)
            if expected_version_id and expected_version_id in version_library:
                lib_item = version_library[expected_version_id]
                criteria_list = lib_item['criteria']
                TOTAL_CRITERIA_COUNT = len(criteria_list)
                
                total_penalty = 0
                met_count = 0
                failed_reasons = []
                
                # Thực hiện vòng lặp tính điểm dựa trên scores hiện hành
                for idx, crit in enumerate(criteria_list):
                    defect_key = crit['defect']
                    defect_name = crit.get('name_vi', defect_key)
                    val = scores.get(defect_key, 0)
                    allowed_range = crit.get('range', [])
                    ideal_target = allowed_range[0] if allowed_range else 1
                    weight = TOTAL_CRITERIA_COUNT - idx 
                    
                    if val == 0: 
                        penalty = weight * 25
                        total_penalty += penalty
                        failed_reasons.append(f"{defect_name}:Thiếu")
                    elif val in allowed_range:
                        met_count += 1
                    else:
                        if allowed_range:
                            closest_limit = min(allowed_range, key=lambda x: abs(x - val))
                            dist = abs(val - closest_limit)
                        else:
                            dist = abs(val - ideal_target)
                        penalty = weight * dist * 5
                        total_penalty += penalty
                        failed_reasons.append(f"{defect_name}:C{val}(Lệch {dist})")

                match_pct = round((met_count / TOTAL_CRITERIA_COUNT) * 100, 1) if TOTAL_CRITERIA_COUNT > 0 else 0
                match_ratio = f"{met_count}/{TOTAL_CRITERIA_COUNT}"
                failed_msg_str = ', '.join(failed_reasons)

                # KIỂM TRA XEM DỮ LIỆU TÍNH RA CÓ LỆCH VỚI DATABASE KHÔNG
                is_tdc_changed = (used_version_id != expected_version_id)
                is_score_changed = (c.get('alloc_penalty') != total_penalty) or (c.get('alloc_match_pct') != match_pct)

                # Chỉ auto-heal update database nếu thực sự có thay đổi (chưa có TDC, sai TDC, hoặc sai Điểm)
                if (used_version_id is None) or (is_pure_sap and is_tdc_changed) or is_score_changed:
                    c['is_auto_calculated'] = True
                    c['alloc_penalty'] = total_penalty
                    c['alloc_match_pct'] = match_pct
                    c['alloc_match_ratio'] = match_ratio
                    c['alloc_failed_msg'] = failed_msg_str
                    c['allocated_tdc_id'] = expected_version_id
                    
                    coils_to_update_db.append((expected_version_id, total_penalty, match_pct, match_ratio, failed_msg_str, c['coil_id']))
                else:
                    # Nếu DB đã đúng chuẩn, ta chỉ cần map lại các biến cho UI hiển thị
                    c['alloc_penalty'] = total_penalty
                    c['alloc_match_pct'] = match_pct
                    c['alloc_match_ratio'] = match_ratio
                    c['alloc_failed_msg'] = failed_msg_str

            else:
                # Không tìm thấy TDC nào khớp
                c['is_missing_tdc'] = True
                c['alloc_penalty'] = -1

            # --- ĐỒNG BỘ UI VARIABLES ---
            c['penalty'] = c['alloc_penalty'] if c['alloc_penalty'] is not None else -1
            c['match_pct'] = c['alloc_match_pct'] if c['alloc_match_pct'] is not None else 0
            if c['alloc_match_ratio']: c['match_ratio'] = c['alloc_match_ratio']
            else: c['match_ratio'] = ""
            
            # Tính toán Sort Priority để xếp hạng lỗi
            sort_diffs = [] 
            if used_version_id and used_version_id in version_library:
                criteria_list = version_library[used_version_id]['criteria']
                for crit in criteria_list:
                    val = scores.get(crit['defect'], 0)
                    target = crit.get('target', 1)
                    allowed_range = crit.get('range', [])
                    if val == 0: sort_diffs.append(99)
                    elif allowed_range and val in allowed_range: sort_diffs.append(0)
                    else: sort_diffs.append(abs(val - target))
            c['_sort_priority'] = tuple(sort_diffs)
            
            allocated_coils.append(c)

        # 6. AUTO-HEALING: LƯU KẾT QUẢ TÍNH TOÁN VÀO DATABASE
        try:
            if coils_to_update_db:
                update_sql = """
                    UPDATE coil_data 
                    SET allocated_tdc_id = ?, alloc_penalty = ?, alloc_match_pct = ?, 
                        alloc_match_ratio = ?, alloc_failed_msg = ?
                    WHERE coil_id = ?
                """
                cursor.executemany(update_sql, coils_to_update_db)
            
            if details_to_insert_db:
                for d in details_to_insert_db:
                    so, mat, cust, grade, thick, width, tdc = d
                    # Đảm bảo header tồn tại
                    cursor.execute("SELECT 1 FROM sales_orders WHERE so_number = ?", (so,))
                    if not cursor.fetchone():
                        cursor.execute("INSERT INTO sales_orders (so_number, customer_name, created_at, status) VALUES (?, ?, ?, 'Synced')", (so, cust, now_str))
                    
                    # Cập nhật hoặc Thêm detail
                    cursor.execute("SELECT id FROM so_details WHERE so_number = ? AND material_code = ?", (so, mat))
                    if not cursor.fetchone():
                        cursor.execute("""
                            INSERT INTO so_details (so_number, material_code, description, grade, thickness, width, total_weight, tdc_id, status)
                            VALUES (?, ?, '[Auto SAP Sync]', ?, ?, ?, 0, ?, 'Synced')
                        """, (so, mat, grade, thick, width, tdc))
            
            if coils_to_update_db or details_to_insert_db:
                conn.commit()
                print(f"🔄 Auto-heal: {len(coils_to_update_db)} coils, {len(details_to_insert_db)} SO details.")

        except Exception as ex:
            print(f"Lỗi Auto-heal DB: {ex}")
            if conn: conn.rollback()

        # 7. SẮP XẾP KẾT QUẢ ĐỂ HIỂN THỊ
        allocated_coils.sort(key=lambda x: (
            0 if x['penalty'] == 0 else (2 if x['penalty'] == -1 else 1),   
            x['penalty'],                    
            x.get('_sort_priority', ()),             
            -x['match_pct']                  
        ))
        
        return jsonify({'coils': allocated_coils})

    except Exception as e:
        print(f"History API Error: {str(e)}")
        import traceback
        traceback.print_exc()
        return jsonify({'orders': [], 'coils': [], 'msg': str(e)})
    finally:
        if conn: conn.close()

@alloc_hist_bp.route('/api/release_coils', methods=['POST'])
def release_coils():
    conn = None
    try:
        req = request.json
        coil_ids = req.get('coil_ids', [])
        current_user = session.get('user_name', 'Unknown') 
        
        if not coil_ids: 
            return jsonify({'status': 'error', 'msg': 'Chưa chọn cuộn nào'})
        
        conn = db.get_connection()
        cursor = conn.cursor()
        now = datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")

        placeholders = ','.join(['?'] * len(coil_ids))
        
        # 1. Lấy thông tin cũ để ghi log
        sql_check = f"SELECT coil_id, allocated_order FROM coil_data WHERE coil_id IN ({placeholders})"
        # LƯU Ý QUAN TRỌNG: convert list sang tuple để execute
        cursor.execute(sql_check, tuple(coil_ids))
        coils_info = cursor.fetchall()

        # 2. Update về NULL (Reset)
        sql_update = f"""
            UPDATE coil_data 
            SET allocated_to = NULL, 
                allocated_order = NULL, 
                allocated_at = NULL, 
                allocated_material = NULL, 
                alloc_note = NULL,
                alloc_penalty = NULL, 
                alloc_match_pct = NULL, 
                alloc_match_ratio = NULL, 
                alloc_failed_msg = NULL, 
                allocated_tdc_id = NULL 
            WHERE coil_id IN ({placeholders})
        """
        cursor.execute(sql_update, tuple(coil_ids))
        
        # 3. Ghi log
        for row in coils_info:
            cid = row[0]
            so_num = str(row[1]).strip() if row[1] else 'N/A'
            log_desc = f"Gỡ bỏ cuộn {cid} ra khỏi đơn hàng {so_num}"
            cursor.execute("""
                INSERT INTO action_history (action_type, ref_id, description, user_name, created_at)
                VALUES (?, ?, ?, ?, ?)
            """, ('RELEASE_ITEM', so_num, log_desc, current_user, now))

        conn.commit()
        return jsonify({'status': 'success', 'msg': f'Đã gỡ và ghi log {len(coil_ids)} cuộn.'})

    except Exception as e:
        if conn: conn.rollback()
        print(f"Release Error: {str(e)}")
        return jsonify({'status': 'error', 'msg': str(e)})
    finally:
        if conn: conn.close()
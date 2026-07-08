from flask import Blueprint, jsonify, request,render_template,send_file
import logging
import pandas as pd
import io
import math
# Import các hàm cần thiết từ db.py của bạn
from db import get_connection, fetchall_as_dict, log_audit

order_rules_bp = Blueprint('order_rules', __name__)
logger = logging.getLogger(__name__)

@order_rules_bp.route('/order_rules', methods=['GET'])
def order_rules_page():
    # Render ra file giao diện bạn vừa tạo
    return render_template('order_rules.html')
# --- 1. LẤY DANH SÁCH ORDER ---
@order_rules_bp.route('/api/orders/options', methods=['GET'])
def get_order_options():
    conn = get_connection()
    try:
        cursor = conn.cursor()
        
        cursor.execute("SELECT DISTINCT KySanXuat FROM order_production_rules WITH(NOLOCK) WHERE KySanXuat IS NOT NULL ORDER BY KySanXuat DESC")
        ky_sx = [r[0] for r in cursor.fetchall()]

        cursor.execute("SELECT DISTINCT m.customer_name FROM order_production_rules opr WITH(NOLOCK) JOIN tdc_versions v ON opr.target_tdc_version_id = v.id JOIN tdc_master m ON v.master_id = m.id WHERE m.customer_name IS NOT NULL ORDER BY m.customer_name")
        customers = [r[0] for r in cursor.fetchall()]

        cursor.execute("SELECT DISTINCT SO_mapping FROM order_production_rules WITH(NOLOCK) WHERE SO_mapping IS NOT NULL ORDER BY SO_mapping DESC")
        sos = [r[0] for r in cursor.fetchall()]

        return jsonify({'status': 'success', 'ky_sx': ky_sx, 'customers': customers, 'sos': sos})
    except Exception as e:
        return jsonify({'status': 'error', 'msg': str(e)})
    finally:
        if conn: conn.close()
@order_rules_bp.route('/api/orders', methods=['GET'])
def get_orders():
    # Nhận tham số từ Frontend
    status_filter = request.args.get('status', 'all')
    search_keyword = request.args.get('search', '').strip()
    page = int(request.args.get('page', 1))
    limit = int(request.args.get('limit', 50))
    offset = (page - 1) * limit
    ky_sx = request.args.get('ky_sx', '')
    customer = request.args.get('customer', '')
    so_mapping = request.args.get('so_mapping', '')
    prod_status = request.args.get('prod_status', '')
    skin = request.args.get('skin', '')
    conn = get_connection()
    try:
        cursor = conn.cursor()
        
        # 1. Xây dựng điều kiện lọc (WHERE)
        where_clauses = ["1=1"]
        params = []
        
        if status_filter == 'conflict':
            where_clauses.append("opr.is_conflict = 1")
        elif status_filter == 'manual':
            where_clauses.append("opr.is_manual_override = 1")
        elif status_filter == 'normal':
            where_clauses.append("ISNULL(opr.is_conflict, 0) = 0 AND ISNULL(opr.is_manual_override, 0) = 0")
            
        if search_keyword:
            # Tìm trong Order, Mô tả, Khách hàng hoặc Mác thép
            where_clauses.append("(opr.[Order] LIKE ? OR opr.material_desc LIKE ? OR m.customer_name LIKE ? OR m.grade LIKE ?)")
            search_term = f"%{search_keyword}%"
            params.extend([search_term, search_term, search_term, search_term])
        if ky_sx:
            where_clauses.append("opr.KySanXuat = ?")
            params.append(ky_sx)
        if customer:
            where_clauses.append("m.customer_name = ?")
            params.append(customer)
        if so_mapping:
            where_clauses.append("opr.SO_mapping = ?")
            params.append(so_mapping)
        if prod_status:
            where_clauses.append("opr.production_status = ?")
            params.append(prod_status)
        if skin:
            where_clauses.append("ISNULL(opr.is_skin_required, 0) = ?")
            params.append(int(skin))    
        where_sql = " AND ".join(where_clauses)
        
        # 2. ĐẾM TỔNG SỐ RECORD (Dùng để Frontend vẽ nút phân trang)
        count_query = f"""
            SELECT COUNT(*) 
            FROM [dbo].[order_production_rules] opr WITH(NOLOCK)
            LEFT JOIN [dbo].[tdc_versions] v WITH(NOLOCK) ON opr.target_tdc_version_id = v.id
            LEFT JOIN [dbo].[tdc_master] m WITH(NOLOCK) ON v.master_id = m.id
            WHERE {where_sql}
        """
        cursor.execute(count_query, params)
        total_records = cursor.fetchone()[0]
        total_pages = math.ceil(total_records / limit) if limit > 0 else 1

        # 3. TRUY VẤN CẮT ĐÚNG SỐ DÒNG CẦN THIẾT (OFFSET ... FETCH)
        data_query = f"""
            SELECT 
                opr.[Order], 
                opr.SO_mapping,
                opr.KySanXuat,
                opr.material_desc,
                opr.production_status,
                ISNULL(opr.is_skin_required, 0) AS is_skin_required,
                ISNULL(opr.total_weight, 0) AS total_weight,
                ISNULL(opr.fulfilled_weight, 0) AS fulfilled_weight,
                opr.target_tdc_version_id,
                opr.req_min_w, 
                opr.req_max_w,
                opr.req_thick,
                opr.req_width,
                opr.alloc_thick,
                ISNULL(opr.is_manual_override, 0) AS is_manual_override,
                ISNULL(opr.is_conflict, 0) AS is_conflict,
                opr.conflict_note,
                opr.proposed_tdc_version_id,
                opr.proposed_min_w,
                opr.proposed_max_w,
                v.version_no AS target_version_no,
                m.tdc_code AS target_tdc_code,
                
                -- 🌟 ĐÃ BỔ SUNG LẠI 6 CỘT NÀY ĐỂ FRONTEND HIỂN THỊ
                m.customer_name,
                m.grade,
                m.usage_purpose,
                pv.version_no AS proposed_version_no,
                pm.tdc_code AS proposed_tdc_code,
                pm.customer_name AS prop_customer_name,
                pm.grade AS prop_grade,
                pm.usage_purpose AS prop_usage_purpose

            FROM [dbo].[order_production_rules] opr WITH(NOLOCK)
            LEFT JOIN [dbo].[tdc_versions] v WITH(NOLOCK) ON opr.target_tdc_version_id = v.id
            LEFT JOIN [dbo].[tdc_master] m WITH(NOLOCK) ON v.master_id = m.id
            LEFT JOIN [dbo].[tdc_versions] pv WITH(NOLOCK) ON opr.proposed_tdc_version_id = pv.id
            LEFT JOIN [dbo].[tdc_master] pm WITH(NOLOCK) ON pv.master_id = pm.id
            WHERE {where_sql}
            ORDER BY opr.[Order] DESC
            OFFSET ? ROWS FETCH NEXT ? ROWS ONLY
        """
        
        # Thêm biến offset và limit vào params
        params.extend([offset, limit])
        cursor.execute(data_query, params)
        rows = fetchall_as_dict(cursor)

        # 4. Trả về payload cực nhẹ
        return jsonify({
            'status': 'success',
            'data': rows,
            'pagination': {
                'page': page,
                'limit': limit,
                'total_records': total_records,
                'total_pages': total_pages
            }
        })

    except Exception as e:
        import traceback
        return jsonify({'status': 'error', 'msg': f"Lỗi: {str(e)}\n{traceback.format_exc()}"}), 500
    finally:
        if conn: conn.close()
# --- 2. CASCADING OPTIONS: LẤY DANH SÁCH CUSTOMER ---
# @order_rules_bp.route('/api/options/customers', methods=['GET'])
# def get_customers():
#     conn = get_connection()
#     try:
#         cursor = conn.cursor()
#         cursor.execute("SELECT DISTINCT customer_name FROM tdc_master WHERE is_deleted = 0 ORDER BY customer_name")
#         rows = cursor.fetchall()
#         return jsonify([row[0] for row in rows if row[0]])
#     except Exception as e:
#         return jsonify({"error": str(e)}), 500
#     finally:
#         conn.close()

# # --- 3. CASCADING OPTIONS: LẤY GRADE THEO CUSTOMER ---
# @order_rules_bp.route('/api/options/grades/<customer>', methods=['GET'])
# def get_grades(customer):
#     conn = get_connection()
#     try:
#         cursor = conn.cursor()
#         cursor.execute("SELECT DISTINCT grade FROM tdc_master WHERE customer_name = ? AND is_deleted = 0 ORDER BY grade", (customer,))
#         rows = cursor.fetchall()
#         return jsonify([row[0] for row in rows if row[0]])
#     except Exception as e:
#         return jsonify({"error": str(e)}), 500
#     finally:
#         conn.close()

# # --- 4. CASCADING OPTIONS: LẤY VERSION THEO MÁC THÉP/KHÁCH HÀNG ---
# @order_rules_bp.route('/api/options/versions', methods=['GET'])
# def get_tdc_versions():
#     cust = request.args.get('customer')
#     grade = request.args.get('grade')
#     purpose = request.args.get('purpose') # Lấy thêm purpose
#     conn = get_connection()
#     try:
#         cursor = conn.cursor()
#         query = """
#             SELECT v.id, v.version_no 
#             FROM tdc_versions v
#             JOIN tdc_master m ON v.master_id = m.id
#             WHERE m.customer_name = ? AND m.grade = ? AND m.usage_purpose = ? 
#             AND v.status = 'Active' AND m.is_deleted = 0
#         """
#         cursor.execute(query, (cust, grade, purpose))
#         rows = cursor.fetchall()
#         return jsonify([{"id": row[0], "name": f"V{row[1]}"} for row in rows])
#     except Exception as e:
#         return jsonify({"error": str(e)}), 500
#     finally:
#         conn.close()

# # --- 5. CẬP NHẬT THỦ CÔNG (CRUD - SAVE) ---
# @order_rules_bp.route('/api/orders/<order_id>', methods=['POST'])
# def save_manual_rule(order_id):
#     data = request.json
#     try:
#         req_min_w = float(data.get('req_min_w', 0))
#         req_max_w = float(data.get('req_max_w', 0))
#         new_tdc_id = str(data.get('tdc_version_id'))
#         new_so = data.get('so_mapping', '')
#         new_prod_status = data.get('production_status', 'MTS')
        
#         if req_max_w <= 0: return jsonify({"error": "Khối lượng Max phải > 0!"}), 400
#         if req_max_w < req_min_w: return jsonify({"error": "Khối lượng Max không được nhỏ hơn Min!"}), 400
#     except ValueError:
#         return jsonify({"error": "Dữ liệu khối lượng không hợp lệ!"}), 400

#     conn = get_connection()
#     try:
#         cursor = conn.cursor()
        
#         # 1. Lấy trạng thái Order CŨ trước khi ghi đè
#         cursor.execute("SELECT target_tdc_version_id, SO_mapping FROM [dbo].[order_production_rules] WHERE [Order] = ?", (order_id,))
#         old_order = cursor.fetchone()

#         if old_order:
#             old_tdc_id = str(old_order[0])
#             old_so = old_order[1] or ''

#             # 2. UPDATE BẢNG RULE CHÍNH (Thay đổi Kế hoạch)
#             query = """
#                 UPDATE [dbo].[order_production_rules]
#                 SET target_tdc_version_id = ?, req_min_w = ?, req_max_w = ?,
#                     SO_mapping = ?, production_status = ?,
#                     is_manual_override = 1, is_conflict = 0, conflict_note = NULL
#                 WHERE [Order] = ?
#             """
#             cursor.execute(query, (new_tdc_id, req_min_w, req_max_w, new_so, new_prod_status, order_id))
#             action_desc = f"Cập nhật tay TDC: {new_tdc_id} | SO: {new_so}"

#             # =================================================================
#             # 🌟 LOGIC MAPPING SO (Không đụng chạm vào qc_status hay điểm số)
#             # =================================================================
            
#             # Cập nhật thông số kỹ thuật (Min/Max) và Cờ Thương mại (SO) cho các cuộn thép thuộc Order này.
#             # CHÚ Ý: Chỉ thay cờ cho những cuộn đang giữ cờ SO Cũ, hoặc cờ '1' (Chờ SO).
#             # Những cuộn đã bị Hạ cấp thành SCRAP (cờ '0') thì không được lôi kéo nó về lại Đơn hàng!
#             update_coil_query = """
#                 UPDATE coil_data
#                 SET req_min_w = ?, 
#                     req_max_w = ?, 
#                     mapped_po = CASE 
#                         WHEN mapped_po = ? OR mapped_po = '1' THEN ? 
#                         ELSE mapped_po 
#                     END
#                 WHERE [Order] = ?
#             """
#             cursor.execute(update_coil_query, (req_min_w, req_max_w, old_so, new_so, order_id))
#         conn.commit()
#         log_audit(action_type="UPSERT_ORDER_RULE", ref_id=order_id, description=action_desc, user_name="QC_Admin")
            
#         return jsonify({"status": "success"})
#     except Exception as e:
#         conn.rollback()
#         logger.error(f"Lỗi SAVE manual rule: {e}")
#         return jsonify({"error": str(e)}), 500
#     finally:
#         if conn: conn.close()
# @order_rules_bp.route('/api/options/purposes', methods=['GET'])
# def get_purposes():
#     cust = request.args.get('customer')
#     grade = request.args.get('grade')
#     conn = get_connection()
#     try:
#         cursor = conn.cursor()
#         cursor.execute("""
#             SELECT DISTINCT usage_purpose 
#             FROM tdc_master 
#             WHERE customer_name = ? AND grade = ? AND is_deleted = 0
#             ORDER BY usage_purpose
#         """, (cust, grade))
#         rows = cursor.fetchall()
#         return jsonify([row[0] for row in rows if row[0]])
#     except Exception as e:
#         return jsonify({"error": str(e)}), 500
#     finally:
#         conn.close()
# @order_rules_bp.route('/api/orders/<order_id>/unlock', methods=['POST'])
# def unlock_order_rule(order_id):
#     conn = get_connection()
#     try:
#         cursor = conn.cursor()
#         query = """
#             UPDATE [dbo].[order_production_rules]
#             SET is_manual_override = 0, is_conflict = 0, conflict_note = NULL,
#                 proposed_tdc_version_id = NULL, proposed_min_w = NULL, proposed_max_w = NULL
#             WHERE [Order] = ?
#         """
#         cursor.execute(query, (order_id,))
#         conn.commit()
#         log_audit(action_type="UNLOCK_ORDER_RULE", ref_id=order_id, description="Mở khóa Order, trả quyền quản lý cho hệ thống Auto (Excel)", user_name="Admin")
#         return jsonify({"status": "success"})
#     except Exception as e:
#         conn.rollback()
#         return jsonify({"error": str(e)}), 500
#     finally:
#         conn.close()
# ==========================================
# 1. API: TẢI EXCEL TEMPLATE ORDER NGOÀI KH
# ==========================================
@order_rules_bp.route('/api/orders/template', methods=['GET'])
def download_order_template():
    # 🌟 ĐÃ THÊM CỘT MÁC THÉP VÀO TEMPLATE
    columns = [
        'Order (* Bắt buộc)', 
        'SO_mapping', 
        'Mác Thép (grade)', # <--- THÊM MỚI Ở ĐÂY
        'Mô tả vật tư (material_desc)', 
        'KySanXuat',
        'Tổng KL (total_weight)', 
        'Min Weight (req_min_w)', 
        'Max Weight (req_max_w)',
        'Mã Tiêu Chuẩn (TDC_Code)', 
        'Dày (req_thick)',
        'Rộng (req_width)',
        'Dày phân bổ (alloc_thick)',
        'Yêu cầu Skin (is_skin_required)', 
        'Loại Hình (production_status)'    
    ]
    
    df = pd.DataFrame(columns=columns)
    
    output = io.BytesIO()
    with pd.ExcelWriter(output, engine='openpyxl') as writer:
        df.to_excel(writer, index=False, sheet_name='Import_Orders')
        worksheet = writer.sheets['Import_Orders']
        for col in worksheet.columns:
            max_length = 0
            column = col[0].column_letter
            for cell in col:
                try:
                    if len(str(cell.value)) > max_length:
                        max_length = len(str(cell.value))
                except: pass
            worksheet.column_dimensions[column].width = (max_length + 2)

    output.seek(0)
    return send_file(
        output,
        mimetype='application/vnd.openxmlformats-officedocument.spreadsheetml.sheet',
        as_attachment=True,
        download_name='Template_Order_Ngoai_Ke_Hoach.xlsx'
    )

# ==========================================
# 2. API: UPLOAD EXCEL VÀ VALIDATE
# ==========================================
@order_rules_bp.route('/api/orders/upload', methods=['POST'])
def upload_orders():
    if 'file' not in request.files:
        return jsonify({'status': 'error', 'msg': 'Không tìm thấy file upload!'})
    
    file = request.files['file']
    if file.filename == '':
        return jsonify({'status': 'error', 'msg': 'Chưa chọn file!'})

    conn = get_connection()
    try:
        df = pd.read_excel(file)
        
        # 🌟 ĐÃ THÊM MAPPING CHO MÁC THÉP
        col_mapping = {
            'Order (* Bắt buộc)': 'Order',
            'SO_mapping': 'SO_mapping',
            'Mác Thép (grade)': 'grade', # <--- MAPPING MỚI
            'Mô tả vật tư (material_desc)': 'material_desc',
            'KySanXuat': 'KySanXuat',
            'Tổng KL (total_weight)': 'total_weight',
            'Min Weight (req_min_w)': 'req_min_w',
            'Max Weight (req_max_w)': 'req_max_w',
            'Mã Tiêu Chuẩn (TDC_Code)': 'TDC_Code',
            'Dày (req_thick)': 'req_thick',
            'Rộng (req_width)': 'req_width',
            'Dày phân bổ (alloc_thick)': 'alloc_thick',
            'Yêu cầu Skin (is_skin_required)': 'is_skin_required',
            'Loại Hình (production_status)': 'production_status'
        }
        df.rename(columns=col_mapping, inplace=True)
        
        df = df.dropna(subset=['Order'])
        if df.empty:
            return jsonify({'status': 'error', 'msg': 'File Excel không có dữ liệu Order hợp lệ!'})

        df['Order'] = df['Order'].astype(str).str.strip().str.replace(r'\.0$', '', regex=True)

        cursor = conn.cursor()

        order_list_excel = df['Order'].tolist()
        placeholders = ','.join(['?'] * len(order_list_excel))
        cursor.execute(f"SELECT [Order] FROM [dbo].[order_production_rules] WHERE [Order] IN ({placeholders})", order_list_excel)
        existing_orders = [row[0] for row in cursor.fetchall()]
        
        if existing_orders:
            return jsonify({
                'status': 'error', 
                'msg': f'⛔ LỖI TRÙNG LẶP: Có {len(existing_orders)} Order đã tồn tại trong hệ thống. Vui lòng xóa chúng khỏi Excel.',
                'duplicate_orders': existing_orders
            })

        df_master = pd.read_sql("SELECT id as master_id, tdc_code, customer_name FROM dbo.tdc_master WITH (NOLOCK)", conn)
        df_active_ver = pd.read_sql("SELECT master_id, id as tdc_version_id FROM dbo.tdc_versions WITH (NOLOCK) WHERE status = 'Active'", conn)
        
        df = pd.merge(df, df_master, left_on='TDC_Code', right_on='tdc_code', how='left')
        df = pd.merge(df, df_active_ver, on='master_id', how='left')

        # 🌟 LOGIC THÔNG MINH BẢO VỆ MÁC THÉP:
        # Nếu Đơn hàng KHÔNG CÓ TDC_Code (MTS) nhưng User có nhập Mác thép -> Gắn Mác thép vào đầu chuỗi Mô tả vật tư
        mask = df['tdc_version_id'].isna() & df['grade'].notna()
        df.loc[mask, 'material_desc'] = "[" + df.loc[mask, 'grade'].astype(str) + "] " + df.loc[mask, 'material_desc'].fillna('').astype(str)

        df['is_skin_required'] = pd.to_numeric(df['is_skin_required'], errors='coerce').fillna(0).astype(int)

        def determine_status(row):
            if pd.notna(row.get('production_status')) and str(row.get('production_status')).strip():
                return str(row['production_status']).strip().upper()
            cust = str(row.get('customer_name', '')).strip().upper()
            if cust == 'TDC NỘI BỘ':
                return 'MTS'
            elif pd.notna(row.get('TDC_Code')) and str(row.get('TDC_Code')).strip() != '':
                return 'MTO' 
            else:
                return 'MTS' 

        df['final_production_status'] = df.apply(determine_status, axis=1)

        def clean_val(val):
            if pd.isna(val) or (isinstance(val, float) and math.isnan(val)):
                return None
            return val

        insert_query = """
            INSERT INTO [dbo].[order_production_rules] (
                [Order], SO_mapping, material_desc, KySanXuat, total_weight, 
                req_min_w, req_max_w, target_tdc_version_id, req_thick, req_width, alloc_thick,
                is_manual_override, is_conflict, production_status, is_skin_required
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, 0, 0, ?, ?)
        """
        
        insert_data = []
        for _, row in df.iterrows():
            insert_data.append((
                clean_val(row['Order']), clean_val(row.get('SO_mapping')), clean_val(row.get('material_desc')), clean_val(row.get('KySanXuat')),
                clean_val(row.get('total_weight')), clean_val(row.get('req_min_w')), clean_val(row.get('req_max_w')),
                clean_val(row.get('tdc_version_id')), 
                clean_val(row.get('req_thick')), clean_val(row.get('req_width')), clean_val(row.get('alloc_thick')),
                row['final_production_status'], row['is_skin_required']
            ))

        cursor.executemany(insert_query, insert_data)
        conn.commit()

        for o in order_list_excel:
            log_audit(action_type="IMPORT_OUT_OF_PLAN_ORDER", ref_id=o, description="Upload Excel Order ngoài kế hoạch", user_name="System")

        return jsonify({'status': 'success', 'msg': f'✅ Đã import thành công {len(insert_data)} Order ngoài kế hoạch!'})

    except Exception as e:
        if conn: conn.rollback()
        import traceback
        return jsonify({'status': 'error', 'msg': f'Lỗi hệ thống: {str(e)}\n{traceback.format_exc()}'})
    finally:
        if conn: conn.close()
import pyodbc
import orjson
import os
from datetime import datetime , timedelta
from sqlalchemy import create_engine
import urllib.parse
pyodbc.pooling = True
# CẤU HÌNH KẾT NỐI (Nên để trong biến môi trường hoặc file .env riêng)
SQL_CONFIG = {
    'driver': '{ODBC Driver 17 for SQL Server}',
    'server': 'PCNTT-HPDQ35029\SQLEXPRESS',  # Thay bằng IP Server Production
    'database': 'factory',
    'user': 'sa',           # Thay bằng user thật
    'password': '12345678a@', # Thay bằng pass thật
    'TrustServerCertificate': 'yes'
}
_db_engine = None
def get_connection_string():
    return f"DRIVER={SQL_CONFIG['driver']};SERVER={SQL_CONFIG['server']};DATABASE={SQL_CONFIG['database']};UID={SQL_CONFIG['user']};PWD={SQL_CONFIG['password']};TrustServerCertificate={SQL_CONFIG['TrustServerCertificate']}"

def dict_factory(cursor, row):
    """
    Helper để chuyển row tuple thành dict (giống sqlite3.Row)
    """
    d = {}
    for idx, col in enumerate(cursor.description):
        d[col[0]] = row[idx]
    return d

def get_connection():
    try:
        conn = pyodbc.connect(get_connection_string())
        # SQL Server mặc định autocommit=False.
        # Để giống SQLite trong code cũ, ta có thể để mặc định và gọi commit() thủ công
        return conn
    except Exception as e:
        print(f"❌ DB Connection Error: {e}")
        raise e

# --- CÁC HÀM TRUY VẤN ---

def get_config(key, default=None):
    conn = get_connection()
    try:
        cursor = conn.cursor()
        cursor.execute("SELECT value FROM app_configs WHERE [key] = ?", (key,))
        row = cursor.fetchone()
        return orjson.loads(row[0]) if row else default
    except Exception as e:
        print(f"Get Config Error: {e}")
        return default
    finally:
        conn.close()

def save_config(key, value):
    conn = get_connection()
    try:
        cursor = conn.cursor()
        query = """
        MERGE app_configs AS target
        USING (SELECT ? AS [key], ? AS [value]) AS source
        ON (target.[key] = source.[key])
        WHEN MATCHED THEN
            UPDATE SET [value] = source.[value]
        WHEN NOT MATCHED THEN
            INSERT ([key], [value]) VALUES (source.[key], source.[value]);
        """
        cursor.execute(query, (key, orjson.dumps(value).decode('utf-8')))
        conn.commit()
    finally:
        conn.close()


def save_batch_coils_v2(batch_data):
    if not batch_data: return

    conn = get_connection()
    cursor = conn.cursor()
    try:
        merge_query = """
        MERGE coil_data AS target
        USING (VALUES (
            ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, 
            CAST(? AS NVARCHAR(100)), 
            ?, ? , CAST(? AS NVARCHAR(MAX)), ?               
        )) 
            AS source (
                coil_id, grade, raw_data, scores, is_checked, weight, target_thick, target_width, 
                production_date, slab_grade, factory, Temperature, Speed, quality_level, slab_grade_name,
                target_temp_finish, target_temp_coil, note_qc, TARGET_LV2
            )
        ON target.coil_id = source.coil_id
        
        WHEN MATCHED THEN
            UPDATE SET 
                slab_grade_name = ISNULL(source.slab_grade_name, target.slab_grade_name),
                updated_at = GETDATE(),
                grade = source.grade,
                raw_data = source.raw_data,
                scores = source.scores,
                is_checked = CASE WHEN target.is_checked = 1 THEN 1 ELSE source.is_checked END,
                factory = source.factory,
                weight = CASE WHEN source.weight > 0 THEN source.weight ELSE target.weight END,
                target_thick = CASE WHEN source.target_thick > 0 THEN source.target_thick ELSE target.target_thick END,
                target_width = CASE WHEN source.target_width > 0 THEN source.target_width ELSE target.target_width END,
                target_temp_finish = CASE WHEN source.target_temp_finish > 0 THEN source.target_temp_finish ELSE target.target_temp_finish END,
                target_temp_coil = CASE WHEN source.target_temp_coil > 0 THEN source.target_temp_coil ELSE target.target_temp_coil END,
                TARGET_LV2 = CASE WHEN source.TARGET_LV2 > 0 THEN source.TARGET_LV2 ELSE target.TARGET_LV2 END,
                production_date = ISNULL(source.production_date, target.production_date),
                slab_grade = ISNULL(source.slab_grade, target.slab_grade),
                quality_level = ISNULL(source.quality_level, target.quality_level),
                note_qc = ISNULL(source.note_qc, target.note_qc),
                Temperature = CASE WHEN source.Temperature > 0 THEN source.Temperature ELSE target.Temperature END,
                Speed = CASE WHEN source.Speed > 0 THEN source.Speed ELSE target.Speed END

        WHEN NOT MATCHED THEN
            INSERT (
                coil_id, grade, raw_data, scores, is_checked, 
                weight, target_thick, target_width, production_date, 
                slab_grade, factory, Temperature, Speed, quality_level, 
                updated_at, slab_grade_name,
                target_temp_finish, target_temp_coil, note_qc, TARGET_LV2
            )
            VALUES (
                source.coil_id, source.grade, source.raw_data, source.scores, source.is_checked, 
                source.weight, source.target_thick, source.target_width, source.production_date, 
                source.slab_grade, source.factory, source.Temperature, source.Speed, source.quality_level, 
                GETDATE(), source.slab_grade_name,
                source.target_temp_finish, source.target_temp_coil, source.note_qc, source.TARGET_LV2
            );
        """
        
        params = []
        for item in batch_data:
            raw_json = orjson.dumps(item.get('raw', {})).decode('utf-8')
            scores_json = orjson.dumps(item.get('scores', {})).decode('utf-8')
            
            params.append((
                item['id'],                                  
                item['grade'],                               
                raw_json,                                    
                scores_json,                                 
                item.get('is_checked', 0),                   
                float(item.get('weight') or 0),              
                float(item.get('target_thick') or 0),        
                float(item.get('target_width') or 0),        
                item.get('production_date'),                 
                item.get('slab_grade'),                      
                item.get('factory', 'HRC1'),                 
                float(item.get('Temperature') or 0),         
                float(item.get('Speed') or 0),               
                item.get('quality_level'),
                item.get('slab_grade_name'),
                float(item.get('target_temp_finish') or 0), # TARGET_FM_TEMP_EXIT
                float(item.get('target_temp_coil') or 0) ,
                item.get('note_qc'),
                float(item.get('TARGET_LV2') or 0)
            ))
            
        cursor.executemany(merge_query, params)
        conn.commit()
    except Exception as e:
        print("DB Save Batch Error:", e)
        conn.rollback()
    finally:
        conn.close()
def update_mechanical_data(batch_data):
    """
    Hàm cập nhật riêng cho Cơ tính/TPHH.
    Cho phép ghi đè Raw Data và Scores ngay cả khi is_checked = 1.
    """
    if not batch_data: return

    conn = get_connection()
    cursor = conn.cursor()
    try:
        # Câu lệnh UPDATE trực tiếp, bỏ qua kiểm tra is_checked
        query = """
            UPDATE coil_data 
            SET raw_data = ?, 
                scores = ?, 
                quality_level = ISNULL(?, quality_level),
                updated_at = GETDATE() 
            WHERE coil_id = ?
        """
        
        params = []
        for item in batch_data:
            params.append((
                orjson.dumps(item['raw']).decode('utf-8'),    # Raw data (Đã merge cũ + mới)
                orjson.dumps(item['scores']).decode('utf-8'),
                item.get('quality_level'), # Scores (Đã giữ điểm tay + thêm điểm cơ tính)
                item['id']
            ))
            
        cursor.executemany(query, params)
        conn.commit()
        print(f"✅ DB: Đã update Cơ tính cho {len(batch_data)} cuộn (Giữ nguyên điểm Bề mặt).")
    except Exception as e:
        print("❌ DB Update Mechanical Error:", e)
        conn.rollback()
    finally:
        conn.close()
def get_active_tdc_list():
    conn = get_connection()
    try:
        cursor = conn.cursor()
        query = """
        SELECT m.id, m.tdc_code, m.customer_name, m.usage_purpose, m.grade, 
               v.version_no, v.criteria_json, v.pdf_path, v.valid_from, v.valid_to, v.status, v.id as version_id
        FROM tdc_master m
        JOIN tdc_versions v ON m.id = v.master_id
        WHERE v.status = 'Active'
              AND m.is_deleted = 0
        ORDER BY m.customer_name, v.version_no DESC
        """
        cursor.execute(query)
        columns = [column[0] for column in cursor.description]
        return [dict(zip(columns, row)) for row in cursor.fetchall()]
    finally:
        conn.close()

def get_tdc_pending_list():
    """Lấy danh sách TDC đang chờ duyệt (Pending)"""
    conn = get_connection()
    try:
        cursor = conn.cursor()
        query = """
        SELECT m.id as master_id, m.tdc_code, m.customer_name, m.usage_purpose, m.grade, 
               v.version_no, v.criteria_json, v.pdf_path, v.valid_from, v.valid_to, v.status, v.created_at, v.id as version_id
        FROM tdc_versions v
        JOIN tdc_master m ON v.master_id = m.id
        WHERE v.status = 'Pending'
            AND m.is_deleted = 0
        ORDER BY v.created_at DESC
        """
        cursor.execute(query)
        columns = [column[0] for column in cursor.description]
        return [dict(zip(columns, row)) for row in cursor.fetchall()]
    finally:
        conn.close()

def get_tdc_history(master_id):
    """Lấy lịch sử version của một Master ID kèm thông tin Master"""
    conn = get_connection()
    try:
        cursor = conn.cursor()
        # THÊM CÁC CỘT: m.customer_name, m.usage_purpose, m.grade
        query = """
        SELECT v.*, m.tdc_code, m.customer_name, m.usage_purpose, m.grade 
        FROM tdc_versions v
        JOIN tdc_master m ON v.master_id = m.id
        WHERE v.master_id = ?
        ORDER BY v.version_no DESC
        """
        cursor.execute(query, (master_id,))
        columns = [column[0] for column in cursor.description]
        return [dict(zip(columns, row)) for row in cursor.fetchall()]
    finally:
        conn.close()

def save_tdc_version(data):
    """
    Lưu TDC (Draft/Pending).
    - Nếu có master_id: Tạo version mới cho master đó.
    - Nếu chưa có master_id: Tạo master mới + version 1.
    """
    conn = get_connection()
    try:
        cursor = conn.cursor()
        
        master_id = data.get('master_id')
        
        # 1. Nếu chưa có Master ID -> Insert Master
        if not master_id:
            # Check trùng code
            cursor.execute("SELECT id FROM tdc_master WHERE tdc_code = ?", (data['code'],))
            existing = cursor.fetchone()
            if existing:
                return False, f"Mã TDC {data['code']} đã tồn tại!"

            cursor.execute("""
                INSERT INTO tdc_master (tdc_code, customer_name, usage_purpose, grade)
                VALUES (?, ?, ?, ?)
            """, (data['code'], data['cust'], data['purpose'], data['grade']))
            cursor.execute("SELECT @@IDENTITY")
            master_id = cursor.fetchone()[0]
        else:
            pass
            
        # 2. Determine Version No
        cursor.execute("SELECT MAX(version_no) FROM tdc_versions WHERE master_id = ?", (master_id,))
        row = cursor.fetchone()
        next_ver = (row[0] or 0) + 1
        
        # 3. Insert Version
        valid_from = data.get('valid_from') or None
        valid_to = data.get('valid_to') or None
        status = data.get('status', 'Pending') # Pending or Draft

        sql_ver = """
            INSERT INTO tdc_versions (master_id, version_no, criteria_json, pdf_path, valid_from, valid_to, status, created_at)
            VALUES (?, ?, ?, ?, ?, ?, ?, GETDATE())
        """
        cursor.execute(sql_ver, (master_id, next_ver, orjson.dumps(data['criteria']).decode('utf-8'), data['pdf'], valid_from, valid_to, status))
        
        conn.commit()
        return True, "Lưu thành công!"
    except Exception as e:
        print(f"Error save_tdc_version: {e}")
        conn.rollback()
        return False, str(e)
    finally:
        conn.close()
def check_tdc_overlap(master_id, start_date, end_date, exclude_version_id=None):
    """
    Kiểm tra xem khoảng thời gian (start_date, end_date) có bị trùng với 
    bản ghi Active hoặc Pending nào khác của cùng một Master ID không.
    """
    if not start_date:
        return False, "Thiếu ngày bắt đầu"
    
    conn = get_connection()
    try:
        cursor = conn.cursor()
        
        # Nếu end_date là None (vô thời hạn), dùng một ngày rất xa để so sánh
        check_end = end_date if end_date else '9999-12-31'
        
        query = """
            SELECT v.version_no, v.status, v.valid_from, v.valid_to
            FROM tdc_versions v
            WHERE v.master_id = ? 
              AND v.status IN ('Active', 'Pending')
              AND v.id != ISNULL(?, -1)
              AND v.valid_from <= ?  -- S1 <= E2
              AND (v.valid_to >= ? OR v.valid_to IS NULL) -- E1 >= S2
        """
        # Logic: Một bản ghi v trùng với bản ghi mới nếu:
        # v.valid_from <= new_end AND (v.valid_to >= new_start)
        
        cursor.execute(query, (master_id, exclude_version_id, check_end, start_date))
        conflict = cursor.fetchone()
        
        if conflict:
            msg = f"Trùng lịch với bản v{conflict[0]} ({conflict[1]}: {conflict[2]} đến {conflict[3] or 'vô thời hạn'})"
            return True, msg
            
        return False, ""
    finally:
        conn.close()
def confirm_tdc_version(data): # Đổi tham số thành 'data' để nhận dictionary
    conn = get_connection()
    try:
        cursor = conn.cursor()
        
        # Trích xuất version_id từ dictionary
        version_id = data.get('version_id')
        if not version_id: return False, "Thiếu Version ID"

        # [BỔ SUNG] Cập nhật lại thông tin nếu có thay đổi từ tab Approval
        update_sql = """
            UPDATE tdc_versions 
            SET criteria_json = ?, valid_from = ?, valid_to = ?
            WHERE id = ?
        """
        cursor.execute(update_sql, (
            orjson.dumps(data['criteria']).decode('utf-8'),
            data.get('valid_from'),
            data.get('valid_to'),
            version_id
        ))

        # 1. Lấy thông tin bản mới để xử lý các bản cũ
        cursor.execute("SELECT master_id, valid_from FROM tdc_versions WHERE id = ?", (version_id,))
        row = cursor.fetchone()
        if not row: return False, "Không tìm thấy bản ghi"
        
        master_id, new_valid_from = row
        new_valid_from_dt = datetime.strptime(data['valid_from'], '%Y-%m-%d')
        old_valid_to = (new_valid_from_dt - timedelta(days=1)).strftime('%Y-%m-%d')
        # 2. Update bản cũ (Active -> Expired)
        cursor.execute("""
            UPDATE tdc_versions 
            SET status = 'Expired', valid_to = ?
            WHERE master_id = ? AND status = 'Active' AND id != ?
        """, (old_valid_to or datetime.now(), master_id, version_id))
            
        # 3. Chuyển bản hiện tại sang Active
        cursor.execute("""
            UPDATE tdc_versions 
            SET status = 'Active', confirmed_at = GETDATE()
            WHERE id = ?
        """, (version_id,))
        
        conn.commit()
        return True, "Đã phê duyệt và cập nhật dữ liệu!"
    except Exception as e:
        if conn: conn.rollback()
        print(f"Confirm Error: {e}")
        return False, str(e)
    finally:
        if conn: conn.close()
def reject_tdc_version(version_id, reason=""):
    """
    Từ chối Version:
    - Set status = 'Rejected'
    """
    conn = get_connection()
    try:
        cursor = conn.cursor()
        cursor.execute("UPDATE tdc_versions SET status = 'Rejected' WHERE id = ?", (version_id,))
        conn.commit()
        return True, "Đã từ chối!"
    except Exception as e:
        return False, str(e)
    finally:
        conn.close()

def delete_tdc(master_id):
    conn = None
    try:
        conn = get_connection()
        cursor = conn.cursor()

        # 1. Kiểm tra xem TDC này đã có khiếu nại nào chưa?
        cursor.execute("""
            SELECT COUNT(*) FROM tdc_complaints 
            WHERE master_id = ?
        """, (master_id,))
        complaint_count = cursor.fetchone()[0]

        # 2. Kiểm tra xem TDC này đã từng được 'Active' bao giờ chưa?
        cursor.execute("""
            SELECT COUNT(*) FROM tdc_versions 
            WHERE master_id = ? AND status IN ('Active', 'Replaced')
        """, (master_id,))
        active_history_count = cursor.fetchone()[0]

        # --- LOGIC QUYẾT ĐỊNH ---
        if complaint_count == 0 and active_history_count == 0:
            # TRƯỜNG HỢP 1: Xóa cứng (Hard Delete) vì hoàn toàn là file rác/nháp
            # Phải xóa version trước (Khóa ngoại)
            cursor.execute("DELETE FROM tdc_versions WHERE master_id = ?", (master_id,))
            cursor.execute("DELETE FROM tdc_master WHERE id = ?", (master_id,))
            action_msg = "Đã xóa vĩnh viễn TDC nháp khỏi hệ thống."
            
        else:
            # TRƯỜNG HỢP 2: Xóa mềm (Soft Delete) vì đã có lịch sử sản xuất/khiếu nại
            cursor.execute("UPDATE tdc_master SET is_deleted = 1 WHERE id = ?", (master_id,))
            
            # Cập nhật các version đang Active thành status khác để không bị query nhầm
            cursor.execute("""
                UPDATE tdc_versions 
                SET status = 'Archived' 
                WHERE master_id = ? AND status = 'Active'
            """, (master_id,))
            action_msg = "TDC đã được đưa vào lưu trữ (Xóa mềm) do có chứa lịch sử hệ thống."

        conn.commit()
        return True, action_msg

    except Exception as e:
        if conn: conn.rollback()
        print("Lỗi xóa TDC:", str(e))
        return False, f"Lỗi cơ sở dữ liệu: {str(e)}"
    finally:
        if conn: conn.close()

def save_sales_order(so_number, tdc_id, items):
    conn = get_connection()
    try:
        cursor = conn.cursor()
        # Check exist
        cursor.execute("SELECT id FROM sales_orders WHERE so_number = ?", (so_number,))
        if cursor.fetchone(): return False, "Số SO đã tồn tại!"

        # Insert Header (Dùng GETDATE() thay vì DATE('now'))
        cursor.execute("INSERT INTO sales_orders (so_number, tdc_id, order_date) VALUES (?, ?, GETDATE())", (so_number, tdc_id))
        
        # Lấy ID vừa insert (SCOPE_IDENTITY())
        cursor.execute("SELECT @@IDENTITY") 
        so_id = cursor.fetchone()[0]

        # Insert Details
        detail_query = """
            INSERT INTO so_details (so_id, thick, width, min_weight, max_weight, qty, total_weight)
            VALUES (?, ?, ?, ?, ?, ?, ?)
        """
        detail_params = [(so_id, it['thick'], it['width'], it['min_weight'], it['max_weight'], it['qty'], it['total_weight']) for it in items]
        cursor.executemany(detail_query, detail_params)
        
        conn.commit()
        return True, "Lưu thành công!"
    except Exception as e:
        conn.rollback()
        return False, str(e)
    finally:
        conn.close()
def fetchall_as_dict(cursor):
    """
    Hàm hỗ trợ chuyển đổi kết quả từ SQL Server (Tuple) sang Dictionary
    Để code cũ (row['key']) hoạt động bình thường.
    """
    columns = [column[0] for column in cursor.description]
    return [dict(zip(columns, row)) for row in cursor.fetchall()]
def log_audit(action_type, ref_id, description, user_name='Admin'):
    """
    Hàm ghi lại lịch sử thao tác của người dùng
    - action_type: Loại hành động (ALLOCATE, DELETE, UPDATE...)
    - ref_id: Mã đối tượng bị tác động (Số SO, Mã Cuộn...)
    - description: Mô tả chi tiết
    """
    conn = None
    try:
        conn = get_connection() # Sử dụng hàm kết nối có sẵn của bạn
        cursor = conn.cursor()
        
        sql = """
            INSERT INTO action_history (action_type, ref_id, description, user_name)
            VALUES (?, ?, ?, ?)
        """
        cursor.execute(sql, (action_type, str(ref_id), str(description), user_name))
        conn.commit()
    except Exception as e:
        print(f"❌ LỖI GHI LOG: {str(e)}")
    finally:
        if conn: conn.close()
def get_db_engine():
    """
    Tạo SQLAlchemy Engine để dùng riêng cho Pandas read_sql
    """
    try:
        # Lấy chuỗi kết nối ODBC cũ
        odbc_str = get_connection_string()
        # Mã hóa URL để SQLAlchemy hiểu được chuỗi ODBC
        params = urllib.parse.quote_plus(odbc_str)
        # Tạo connection string chuẩn SQLAlchemy cho SQL Server
        sqlalchemy_conn_str = f"mssql+pyodbc:///?odbc_connect={params}"
        
        # Tạo engine (pool_size tùy chỉnh nếu cần)
        engine = create_engine(sqlalchemy_conn_str)
        return engine
    except Exception as e:
        print(f"❌ SQLAlchemy Engine Error: {e}")
        raise e
def get_complaints_by_master(master_id):
    conn = get_connection()
    cursor = conn.cursor()
    try:
        # [CHUẨN HÓA]: JOIN bảng tdc_versions để lấy version_no chính xác dựa trên version_id
        query = """
            SELECT c.id, c.complaint_date, c.defect_group, c.description, c.resolution_plan, 
                   c.weight_kg, c.amount_vnd, c.status, c.so_number, c.coil_ids, c.pdf_path,
                   v.version_no, c.version_id  
            FROM tdc_complaints c
            LEFT JOIN tdc_versions v ON c.version_id = v.id
            WHERE c.master_id = ? 
            ORDER BY c.complaint_date DESC
        """
        cursor.execute(query, (master_id,))
        columns = [column[0] for column in cursor.description]
        return [dict(zip(columns, row)) for row in cursor.fetchall()]
    except Exception as e:
        print(f"Error in get_complaints_by_master: {str(e)}")
        return []
    finally:
        conn.close()
def update_complaint_details(data):
    conn = get_connection()
    try:
        cursor = conn.cursor()
        query = """
            UPDATE tdc_complaints 
            SET complaint_date = ?, 
                defect_group = ?, 
                weight_kg = ?, 
                amount_vnd = ?, 
                description = ?, 
                resolution_plan = ?,
                status = ?,
                version_id = ?, -- Đã đổi thành version_id
                so_number = ?,
                coil_ids = ?,
                pdf_path = ?
            WHERE id = ?
        """
        cursor.execute(query, (
            data.get('date'),
            data.get('group'),
            data.get('weight'),
            data.get('amount'),
            data.get('desc'),          
            data.get('resolution'),    
            data.get('status'),
            data.get('version_id'), 
            data.get('so_number'), 
            data.get('coil_ids'),  
            data.get('pdf_path'),
            data.get('id')
        ))
        conn.commit()
        return True, "Cập nhật thành công"
    except Exception as e:
        print(f"Update Error: {str(e)}")
        return False, str(e)
    finally:
        conn.close()
def add_complaint(data):
    conn = get_connection()
    try:
        cursor = conn.cursor()
        # [CHUẨN HÓA]: Lưu version_id
        query = """
            INSERT INTO tdc_complaints 
            (master_id, complaint_date, defect_group, weight_kg, amount_vnd, description, resolution_plan, status, version_id, so_number, coil_ids, pdf_path)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """
        cursor.execute(query, (
            data.get('master_id'),
            data.get('date'),         
            data.get('group'),         
            data.get('weight'),
            data.get('amount'),
            data.get('desc'),          
            data.get('resolution'),   
            data.get('status', 'Pending'),
            data.get('version_id'), # Đã đổi thành version_id
            data.get('so_number'),
            data.get('coil_ids'),
            data.get('pdf_path')
        ))
        conn.commit()
        return True, "Lưu thành công"
    except Exception as e:
        print(f"Add Complaint Error: {str(e)}")
        return False, str(e)
    finally:
        conn.close()

def update_complaint_status(comp_id, new_status):
    """Cập nhật nhanh trạng thái (Dùng cho dropdown ở bảng)"""
    conn = get_connection()
    try:
        cursor = conn.cursor()
        cursor.execute("UPDATE tdc_complaints SET status = ? WHERE id = ?", (new_status, comp_id))
        conn.commit()
        return True, "Cập nhật trạng thái thành công"
    except Exception as e:
        return False, str(e)
    finally:
        conn.close()
def get_dashboard_stats(month_filter=None):
    conn = get_connection()
    try:
        cursor = conn.cursor()
        
        # Lọc theo tháng (Nếu có truyền từ UI)
        where_clause = "1=1"
        params = []
        if month_filter:
            where_clause = "FORMAT(c.complaint_date, 'yyyy-MM') = ?"
            params.append(month_filter)

        data = {
            'kpi': {'total_count': 0, 'total_weight': 0, 'total_amount': 0, 'closed_count': 0},
            'status_chart': [],
            'group_chart': [],
            'top_customers': [],
            'trend_chart': []
        }

        # 1. Lấy KPI tổng
        cursor.execute(f"""
            SELECT 
                COUNT(id) as total_count,
                ISNULL(SUM(weight_kg), 0) as total_weight,
                ISNULL(SUM(amount_vnd), 0) as total_amount,
                SUM(CASE WHEN status = 'Closed' THEN 1 ELSE 0 END) as closed_count
            FROM tdc_complaints c
            WHERE {where_clause}
        """, params)
        row = cursor.fetchone()
        if row:
            data['kpi'] = {
                'total_count': row[0], 'total_weight': float(row[1]), 
                'total_amount': float(row[2]), 'closed_count': row[3] or 0
            }

        # 2. Lấy Data Chart Trạng thái
        cursor.execute(f"SELECT status, COUNT(*) FROM tdc_complaints c WHERE {where_clause} GROUP BY status", params)
        data['status_chart'] = [{'status': r[0], 'count': r[1]} for r in cursor.fetchall()]

        # 3. Lấy Data Chart Nhóm lỗi
        cursor.execute(f"SELECT defect_group, COUNT(*) FROM tdc_complaints c WHERE {where_clause} GROUP BY defect_group", params)
        data['group_chart'] = [{'group': r[0], 'count': r[1]} for r in cursor.fetchall()]

        # 4. Lấy Top Khách hàng
        cursor.execute(f"""
            SELECT TOP 5 m.customer_name, COUNT(c.id) as cnt, ISNULL(SUM(c.weight_kg), 0) as wgt
            FROM tdc_complaints c
            JOIN tdc_master m ON c.master_id = m.id
            WHERE {where_clause}
            GROUP BY m.customer_name
            ORDER BY cnt DESC, wgt DESC
        """, params)
        data['top_customers'] = [{'customer_name': r[0], 'count': r[1], 'weight': float(r[2])} for r in cursor.fetchall()]

        # 5. Xu hướng 6 tháng (Bỏ qua filter tháng, luôn lấy 6 tháng lùi lại từ hiện tại)
        cursor.execute("""
            SELECT FORMAT(complaint_date, 'yyyy-MM') as mth, COUNT(id) 
            FROM tdc_complaints 
            WHERE complaint_date >= DATEADD(month, -5, GETDATE())
            GROUP BY FORMAT(complaint_date, 'yyyy-MM')
            ORDER BY mth ASC
        """)
        data['trend_chart'] = [{'month': r[0], 'count': r[1]} for r in cursor.fetchall()]

        return data
    except Exception as e:
        print(f"Error Dashboard: {e}")
        return {}
    finally:
        conn.close()     
# PHẦN MỚI: QUẢN LÝ YÊU CẦU CÔNG NGHỆ (YCCN)
def get_active_yccn_list():
    """
    Lấy danh sách tất cả YCCN đang Active.
    QUAN TRỌNG: Phải lấy đủ các cột phân cấp (factory, process, usage...) để Front-end vẽ cây.
    """
    conn = get_connection()
    try:
        cursor = conn.cursor()
        query = """
            SELECT 
                v.id AS version_id,
                m.id AS master_id,
                m.yccn_code,
                m.category,      -- Phân loại, Mapping, Sales...
                m.title,
                m.factory_code,  -- HRC1, HRC2, CTD
                m.process_stage, -- Luyện, Đúc, Cán
                m.usage_purpose, -- Mục đích sử dụng (hoặc tên folder con)
                v.version_no,
                v.grade_apply,   -- Mác thép
                v.slab_grade,    -- Mác phôi
                v.valid_from,
                v.valid_to,
                v.pdf_path,
                v.status,
                v.created_at,
                v.note
            FROM yccn_master m
            JOIN yccn_versions v ON m.id = v.master_id
            WHERE v.status = 'Active'
            ORDER BY m.factory_code, m.category, m.yccn_code
        """
        cursor.execute(query)
        columns = [column[0] for column in cursor.description]
        return [dict(zip(columns, row)) for row in cursor.fetchall()]
    except Exception as e:
        print("Error getting Active YCCN:", e)
        return []
    finally:
        conn.close()



def get_yccn_history(master_id):
    """Lấy lịch sử các phiên bản của một tài liệu YCCN"""
    conn = get_connection()
    try:
        cursor = conn.cursor()
        query = """
            SELECT 
                v.id,
                v.master_id,
                v.version_no,
                v.grade_apply,
                v.slab_grade,
                v.pdf_path,
                v.valid_from,
                v.valid_to,
                v.status,
                v.note,
                v.created_at,
                v.confirmed_at
            FROM yccn_versions v
            WHERE v.master_id = ?
            ORDER BY v.version_no DESC
        """
        cursor.execute(query, (master_id,))
        columns = [column[0] for column in cursor.description]
        results = []
        for row in cursor.fetchall():
            results.append(dict(zip(columns, row)))
        return results
    except Exception as e:
        print("Error getting YCCN history:", e)
        return []
    finally:
        conn.close()
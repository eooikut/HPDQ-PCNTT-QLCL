import pyodbc
import orjson
import os
from datetime import datetime , timedelta

# CẤU HÌNH KẾT NỐI (Nên để trong biến môi trường hoặc file .env riêng)
SQL_CONFIG = {
    'driver': '{ODBC Driver 17 for SQL Server}',
    'server': 'PCNTT-HPDQ35029',  # Thay bằng IP Server Production
    'database': 'factory',
    'user': 'sa',           # Thay bằng user thật
    'password': '12345678a@', # Thay bằng pass thật
    'TrustServerCertificate': 'yes'
}

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
        # SQL Server dùng MERGE để Upsert cấu hình
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
    conn = get_connection()
    cursor = conn.cursor()
    try:
        # [SỬA 1]: Thêm dấu ? thứ 11 vào dòng VALUES (...)
        # [SỬA 2]: Thêm cột 'factory' vào danh sách cột định nghĩa source (...)
        merge_query = """
        MERGE coil_data AS target
        USING (VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)) 
            AS source (coil_id, grade, raw_data, scores, is_checked, weight, target_thick, target_width, production_date, slab_grade, factory, Temperature, Speed)
        ON target.coil_id = source.coil_id
        WHEN MATCHED THEN
            UPDATE SET 
                grade = source.grade,
                raw_data = source.raw_data,
                scores = source.scores,
                weight = source.weight,
                target_thick = source.target_thick,
                target_width = source.target_width,
                production_date = source.production_date,
                slab_grade = source.slab_grade,
                factory = source.factory,
                Temperature = source.Temperature, 
                Speed = source.Speed  
        WHEN NOT MATCHED THEN
            -- [SỬA 4]: Thêm cột factory vào câu lệnh INSERT
            INSERT (coil_id, grade, raw_data, scores, is_checked, weight, target_thick, target_width, production_date, slab_grade, factory, Temperature, Speed)
            VALUES (source.coil_id, source.grade, source.raw_data, source.scores, source.is_checked, source.weight, source.target_thick, source.target_width, source.production_date, source.slab_grade, source.factory, source.Temperature, source.Speed);
        """
        
        params = []
        for item in batch_data:
            # Danh sách này của bạn ĐÃ ĐÚNG (có 11 phần tử), lỗi chỉ nằm ở câu SQL trên
            params.append((
                item['id'], 
                item['grade'], 
                orjson.dumps(item['raw']).decode('utf-8'), 
                orjson.dumps(item['scores']).decode('utf-8'), 
                item['is_checked'],
                item.get('weight', 0), 
                item.get('target_thick', 0), 
                item.get('target_width', 0),
                item.get('production_date'),
                item.get('slab_grade'),
                item.get('factory', 'HRC1') ,
                item.get('Temperature', 0), 
                item.get('Speed', 0)
            ))
            
        cursor.executemany(merge_query, params)
        conn.commit()
    except Exception as e:
        print("DB Save Batch Error:", e)
        conn.rollback()
    finally:
        conn.close()

# --- CÁC HÀM GET DỮ LIỆU CŨ CẦN SỬA ĐỂ TRẢ VỀ DICT ---

def get_active_tdc_list():
    conn = get_connection()
    try:
        cursor = conn.cursor()
        query = """
        SELECT m.id, m.tdc_code, m.customer_name, m.usage_purpose, m.grade, 
               v.version_no, v.criteria_json, v.pdf_path, v.valid_from, v.valid_to, v.status, v.id as version_id
        FROM tdc_master m
        JOIN tdc_versions v ON m.id = v.master_id
        WHERE v.status = 'Active' -- CHỈ LẤY BẢN ACTIVE Ở ĐÂY
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
        ORDER BY v.created_at DESC
        """
        cursor.execute(query)
        columns = [column[0] for column in cursor.description]
        return [dict(zip(columns, row)) for row in cursor.fetchall()]
    finally:
        conn.close()

def get_tdc_history(master_id):
    """Lấy lịch sử version của một Master ID"""
    conn = get_connection()
    try:
        cursor = conn.cursor()
        query = """
        SELECT v.*, m.tdc_code 
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
            # Nếu đã có Master, update Master Infor nếu cần (Optional, thường master ít đổi)
            # Ở đây ta giả định Master Infor (Customer, Purpose, Code) không đổi khi ra version mới
            pass
            
        # 2. Determine Version No
        # Lấy max version hiện tại
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

def delete_tdc(tdc_id):
    conn = get_connection()
    try:
        cursor = conn.cursor()
        cursor.execute("SELECT 1 FROM sales_orders WHERE tdc_id = ?", (tdc_id,))
        if cursor.fetchone(): return False
        
        cursor.execute("DELETE FROM tdc_master WHERE id = ?", (tdc_id,))
        conn.commit()
        return True
    finally:
        conn.close()

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
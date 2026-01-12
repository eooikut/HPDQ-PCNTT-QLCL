import pyodbc
import json
import os
from datetime import datetime

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
        return json.loads(row[0]) if row else default
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
        cursor.execute(query, (key, json.dumps(value)))
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
                json.dumps(item['raw']), 
                json.dumps(item['scores']), 
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

def get_tdc_master_list():
    conn = get_connection()
    try:
        cursor = conn.cursor()
        cursor.execute("SELECT * FROM tdc_master ORDER BY customer_name, usage_purpose")
        # Convert tuple sang dict thủ công
        columns = [column[0] for column in cursor.description]
        results = []
        for row in cursor.fetchall():
            results.append(dict(zip(columns, row)))
        return results
    finally:
        conn.close()

def save_tdc_master(data):
    conn = get_connection()
    try:
        cursor = conn.cursor()
        if data.get('id'):
            cursor.execute("""
                UPDATE tdc_master 
                SET tdc_code=?, customer_name=?, usage_purpose=?, grade=?, criteria_json=?, pdf_path=?
                WHERE id=?
            """, (data['code'], data['cust'], data['purpose'], data['grade'], json.dumps(data['criteria']), data['pdf'], data['id']))
        else:
            cursor.execute("""
                INSERT INTO tdc_master (tdc_code, customer_name, usage_purpose, grade, criteria_json, pdf_path)
                VALUES (?, ?, ?, ?, ?, ?)
            """, (data['code'], data['cust'], data['purpose'], data['grade'], json.dumps(data['criteria']), data['pdf']))
        conn.commit()
        return True
    except Exception as e:
        print(f"Error saving TDC: {e}")
        return False
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
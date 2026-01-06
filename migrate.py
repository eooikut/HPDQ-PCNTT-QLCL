import sqlite3
import pyodbc
import json
import os

# --- CẤU HÌNH KẾT NỐI ---
# 1. Đường dẫn file SQLite cũ
SQLITE_DB_FILE = 'qc_database.db'

# 2. Thông tin SQL Server (Production)
SQL_SERVER_CONFIG = {
    'driver': '{ODBC Driver 17 for SQL Server}',
    'server': 'PCNTT-HPDQ35029',         # Thay bằng IP hoặc tên máy chủ của bạn
    'database': 'factory', # Tên DB trên SQL Server
    'user': 'sa',                  # User đăng nhập
    'password': '12345678a@',    # Mật khẩu
    'TrustServerCertificate': 'yes'
}

def get_sql_conn():
    conn_str = f"DRIVER={SQL_SERVER_CONFIG['driver']};SERVER={SQL_SERVER_CONFIG['server']};DATABASE={SQL_SERVER_CONFIG['database']};UID={SQL_SERVER_CONFIG['user']};PWD={SQL_SERVER_CONFIG['password']};TrustServerCertificate={SQL_SERVER_CONFIG['TrustServerCertificate']}"
    return pyodbc.connect(conn_str, autocommit=True)
def clean_date_migration(val):
    """Chuyển đổi các định dạng ngày lạ của SQLite sang chuẩn SQL Server"""
    if val is None: return None
    s = str(val).strip()
    
    # 1. Nếu là chuỗi rỗng hoặc 'None' -> Trả về NULL
    if s == '' or s.lower() == 'none': return None
    
    # 2. Xử lý định dạng có chữ 'T' (2025-01-01T12:00:00)
    s = s.replace('T', ' ')
    
    # 3. Cắt bỏ phần mili-giây thừa (sau dấu chấm)
    if '.' in s: s = s.split('.')[0]
    return s
def clean_float(val):
    """Làm sạch số (tránh chuỗi rỗng)"""
    if val is None or val == '': return 0
    try:
        return float(val)
    except: return 0
def migrate_coil_data():
    print("🚀 Bắt đầu di chuyển bảng 'coil_data'...")
    
    # 1. Đọc từ SQLite
    if not os.path.exists(SQLITE_DB_FILE):
        print(f"❌ Không tìm thấy file {SQLITE_DB_FILE}")
        return

    sqlite_conn = sqlite3.connect(SQLITE_DB_FILE)
    sqlite_conn.row_factory = sqlite3.Row
    sqlite_cursor = sqlite_conn.cursor()
    
    try:
        # Lấy toàn bộ dữ liệu cũ
        # Lưu ý: Chỉ lấy các cột tương thích, nếu SQLite có cột thừa thì bỏ qua
        rows = sqlite_cursor.execute("""
            SELECT coil_id, grade, raw_data, scores, is_checked, 
                   weight, target_thick, target_width, 
                   updated_at, allocated_to, allocated_order, allocated_at,
                   production_date, slab_grade
            FROM coil_data WITH (NOLOCK)
        """).fetchall()
        
        print(f"   -> Tìm thấy {len(rows)} dòng trong SQLite.")
    except Exception as e:
        print(f"⚠️ Lỗi đọc SQLite (Có thể do thiếu cột mới): {e}")
        # Thử lại với query đơn giản hơn nếu schema cũ quá khác
        rows = sqlite_cursor.execute("SELECT * FROM coil_data WITH (NOLOCK)").fetchall()

    sqlite_conn.close()

    # 2. Ghi vào SQL Server
    sql_conn = get_sql_conn()
    cursor = sql_conn.cursor()
    
    # Xóa dữ liệu cũ trên SQL Server để nạp lại sạch sẽ (Tùy chọn - Cẩn thận!)
    # cursor.execute("DELETE FROM coil_data WITH (NOLOCK)") 
    
    success_count = 0
    error_count = 0
    
    query_insert = """
    MERGE coil_data AS target
    USING (VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)) 
        AS source (coil_id, grade, raw_data, scores, is_checked, weight, target_thick, target_width, updated_at, allocated_to, allocated_order, allocated_at, production_date, slab_grade)
    ON target.coil_id = source.coil_id
    WHEN MATCHED THEN
        UPDATE SET 
            grade = source.grade,
            raw_data = source.raw_data,
            scores = source.scores,
            is_checked = source.is_checked,
            weight = source.weight,
            target_thick = source.target_thick,
            target_width = source.target_width,
            production_date = source.production_date,
            slab_grade = source.slab_grade,
            allocated_to = source.allocated_to
    WHEN NOT MATCHED THEN
        INSERT (coil_id, grade, raw_data, scores, is_checked, weight, target_thick, target_width, updated_at, allocated_to, allocated_order, allocated_at, production_date, slab_grade)
        VALUES (source.coil_id, source.grade, source.raw_data, source.scores, source.is_checked, source.weight, source.target_thick, source.target_width, source.updated_at, source.allocated_to, source.allocated_order, source.allocated_at, source.production_date, source.slab_grade);
    """

    for row in rows:
        try:
            # Chuyển đổi Row object thành Dict để dễ xử lý
            item = dict(row)
            
            # Xử lý các trường có thể thiếu trong SQLite cũ
            p_coil_id = str(item['coil_id'])
            p_grade = item.get('grade', 'SAE1006')
            p_raw = item.get('raw_data', '{}')
            p_scores = item.get('scores', '{}')
            p_checked = 1 if item.get('is_checked') else 0 # Chuyển True/False hoặc 1/0 thành bit
            
            # Các trường số
            p_weight = item.get('weight')
            p_t_thick = item.get('target_thick')
            p_t_width = item.get('target_width')
            
            # Các trường text mới
            p_prod_date = clean_date_migration(item.get('production_date'))
            p_slab_grade = item.get('slab_grade')
            p_alloc_to = item.get('allocated_to')
            p_alloc_order = item.get('allocated_order')
            p_alloc_at = item.get('allocated_at')
            p_updated = item.get('updated_at')

            params = (p_coil_id, p_grade, p_raw, p_scores, p_checked, 
                      p_weight, p_t_thick, p_t_width, 
                      p_updated, p_alloc_to, p_alloc_order, p_alloc_at, 
                      p_prod_date, p_slab_grade)

            cursor.execute(query_insert, params)
            success_count += 1
            
        except Exception as e:
            print(f"❌ Lỗi dòng {item.get('coil_id')}: {e}")
            error_count += 1

    sql_conn.commit()
    sql_conn.close()
    print(f"✅ Hoàn tất! Thành công: {success_count} | Lỗi: {error_count}")


if __name__ == "__main__":
    print("--- TOOL MIGRATION: SQLITE TO SQL SERVER ---")
    migrate_coil_data()
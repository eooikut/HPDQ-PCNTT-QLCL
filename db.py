import sqlite3
import json
import os

DB_FILE = 'qc_database.db'

# Định nghĩa cấu trúc bảng ngay đầu file để dễ quản lý
SCHEMA_SQL = """
    CREATE TABLE IF NOT EXISTS app_configs (
        key TEXT PRIMARY KEY,
        value TEXT
    );

    CREATE TABLE IF NOT EXISTS coil_data (
        coil_id TEXT PRIMARY KEY,
        grade TEXT DEFAULT 'SAE1006',
        raw_data TEXT,
        scores TEXT,
        is_checked BOOLEAN DEFAULT 0,
        updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
    );

    -- [MỚI] Bảng lưu yêu cầu TDC Khách hàng
    CREATE TABLE IF NOT EXISTS customer_orders (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        customer_name TEXT,
        grade TEXT,
        qty_req INTEGER, -- Số cuộn yêu cầu
        priority INTEGER DEFAULT 1,
        criteria_json TEXT, -- Lưu danh sách tiêu chí theo thứ tự ưu tiên
        created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
    );
    CREATE TABLE IF NOT EXISTS audit_log (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    coil_id TEXT,
    user_name TEXT, -- Hiện tại chưa có login, có thể để mặc định 'Admin' hoặc 'User'
    defect_key TEXT,
    old_value REAL,
    new_value REAL,
    changed_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);
"""

def get_connection():
    """
    Tạo kết nối đến DB. 
    Cơ chế TỰ PHỤC HỒI: Nếu kết nối vào mà thấy thiếu bảng (do file bị xóa),
    sẽ tự động chạy lệnh tạo bảng ngay lập tức.
    """
    conn = sqlite3.connect(DB_FILE,timeout=10.0)
    conn.row_factory = sqlite3.Row
    
    # Kiểm tra xem bảng coil_data đã có chưa
    try:
        conn.execute("SELECT 1 FROM coil_data LIMIT 1")
    except sqlite3.OperationalError:
        # Nếu lỗi (tức là chưa có bảng), thực thi lệnh tạo bảng
        print("⚠️ Phát hiện Database trống hoặc bị xóa. Đang khởi tạo lại bảng...")
        with conn:
            conn.executescript(SCHEMA_SQL)
            
    return conn

# --- CÁC HÀM CONFIG ---
def get_config(key, default=None):
    conn = get_connection()
    try:
        row = conn.execute("SELECT value FROM app_configs WHERE key = ?", (key,)).fetchone()
        return json.loads(row['value']) if row else default
    except:
        return default
    finally:
        conn.close()

def save_config(key, value):
    conn = get_connection()
    conn.execute("REPLACE INTO app_configs (key, value) VALUES (?, ?)", (key, json.dumps(value)))
    conn.commit()
    conn.close()

# --- CÁC HÀM DATA CUỘN (CORE) ---
def upsert_coil_raw(coil_id, new_raw_data, grade=None):
    """Cập nhật dữ liệu thô (Merge cũ + mới)"""
    conn = get_connection()
    try:
        row = conn.execute("SELECT raw_data, grade FROM coil_data WHERE coil_id = ?", (coil_id,)).fetchone()
        
        current_raw = {}
        current_grade = 'SAE1006' 
        
        if row:
            if row['raw_data']: current_raw = json.loads(row['raw_data'])
            if row['grade']: current_grade = row['grade']
        
        current_raw.update(new_raw_data)
        final_grade = grade if grade else current_grade

        conn.execute('''
            INSERT INTO coil_data (coil_id, grade, raw_data) 
            VALUES (?, ?, ?)
            ON CONFLICT(coil_id) DO UPDATE SET
            grade = excluded.grade,
            raw_data = excluded.raw_data,
            updated_at = CURRENT_TIMESTAMP
        ''', (coil_id, final_grade, json.dumps(current_raw)))
        
        conn.commit()
        return current_raw, final_grade
    finally:
        conn.close()
def save_batch_coils_v2(batch_data):
    conn = get_connection()
    for item in batch_data:
        # Update thông tin cơ bản + 3 cột mới
        conn.execute("""
            UPDATE coil_data 
            SET grade=?, raw_data=?, scores=?, is_checked=?, 
                weight=?, target_thick=?, target_width=?
            WHERE coil_id=?
        """, (
            item['grade'], 
            json.dumps(item['raw']), 
            json.dumps(item['scores']), 
            item['is_checked'],
            item['weight'], 
            item['target_thick'], 
            item['target_width'],
            item['id']
        ))
        
        # Insert nếu chưa có (Dùng INSERT OR IGNORE xong Update, hoặc Upsert)
        # Để đơn giản, ta dùng INSERT OR IGNORE trước để đảm bảo row tồn tại
        conn.execute("INSERT OR IGNORE INTO coil_data (coil_id) VALUES (?)", (item['id'],))
        
        # Update lại lần nữa để chắc chắn (Pattern lười biếng nhưng an toàn cho SQLite)
        conn.execute("""
            UPDATE coil_data 
            SET grade=?, raw_data=?, scores=?, is_checked=?, 
                weight=?, target_thick=?, target_width=?
            WHERE coil_id=?
        """, (
            item['grade'], json.dumps(item['raw']), json.dumps(item['scores']), 
            item['is_checked'], item['weight'], item['target_thick'], item['target_width'], item['id']
        ))
    conn.commit()
    conn.close()
def save_coil_scores(coil_id, scores):
    """Lưu điểm số (Merge cũ + mới)"""
    conn = get_connection()
    try:
        row = conn.execute("SELECT scores FROM coil_data WHERE coil_id = ?", (coil_id,)).fetchone()
        current_scores = json.loads(row['scores']) if row and row['scores'] else {}
        current_scores.update(scores)
        conn.execute("UPDATE coil_data SET scores = ? WHERE coil_id = ?", (json.dumps(current_scores), coil_id))
        conn.commit()
    finally:
        conn.close()

def save_batch_coils(data_list):
    """
    Lưu lô lớn (Batch Insert) - Dùng cho Upload để tăng tốc độ
    """
    conn = get_connection()
    try:
        conn.execute("BEGIN TRANSACTION")
        for item in data_list:
            coil_id = item['id']
            new_grade = item['grade']
            new_raw = item['raw']
            new_scores = item['scores']
            
            # Lấy dữ liệu cũ để merge
            row = conn.execute("SELECT raw_data, scores, grade FROM coil_data WHERE coil_id = ?", (coil_id,)).fetchone()
            
            current_raw = {}
            current_scores = {}
            final_grade = new_grade if new_grade else (row['grade'] if row else 'SAE1006')

            if row:
                if row['raw_data']: current_raw = json.loads(row['raw_data'])
                if row['scores']: current_scores = json.loads(row['scores'])
            
            current_raw.update(new_raw)
            current_scores.update(new_scores)
            
            conn.execute('''
                INSERT INTO coil_data (coil_id, grade, raw_data, scores, updated_at) 
                VALUES (?, ?, ?, ?, CURRENT_TIMESTAMP)
                ON CONFLICT(coil_id) DO UPDATE SET
                grade = excluded.grade,
                raw_data = excluded.raw_data,
                scores = excluded.scores,
                updated_at = CURRENT_TIMESTAMP
            ''', (coil_id, final_grade, json.dumps(current_raw), json.dumps(current_scores)))
            
        conn.execute("COMMIT")
    except Exception as e:
        conn.execute("ROLLBACK")
        print(f"Batch Error: {e}")
        raise e
    finally:
        conn.close()

def load_all_data_for_dashboard():
    """Load toàn bộ dữ liệu ra dashboard"""
    conn = get_connection()
    try:
        rows = conn.execute("SELECT coil_id, scores, grade, is_checked, raw_data FROM coil_data").fetchall()
        radar_data = {}
        for r in rows:
            # Chỉ load những cuộn có điểm
            if r['scores']:
                s = json.loads(r['scores'])
                s['IS_CHECKED'] = bool(r['is_checked'])
                s['GRADE'] = r['grade']
                # Cần raw_data để tính Heatmap
                raw = json.loads(r['raw_data']) if r['raw_data'] else {}
                
                radar_data[r['coil_id']] = {
                    'scores': s,
                    'raw_data': raw,
                    'GRADE': r['grade'],
                    'IS_CHECKED': bool(r['is_checked'])
                }
        return radar_data
    except Exception as e:
        print(f"DB Load Error: {e}")
        return {}
    finally:
        conn.close()
# --- CẬP NHẬT HÀM LƯU (HỖ TRỢ UPDATE) ---
def save_customer_order(name, grade, qty, criteria, order_id=None):
    """
    Lưu đơn hàng/TDC.
    - Nếu có order_id -> UPDATE
    - Nếu order_id is None -> INSERT
    """
    conn = get_connection()
    try:
        if order_id:
            # Logic Sửa
            conn.execute('''
                UPDATE customer_orders 
                SET customer_name=?, grade=?, qty_req=?, criteria_json=?, created_at=CURRENT_TIMESTAMP
                WHERE id=?
            ''', (name, grade, qty, json.dumps(criteria), order_id))
        else:
            # Logic Thêm mới
            conn.execute('''
                INSERT INTO customer_orders (customer_name, grade, qty_req, criteria_json)
                VALUES (?, ?, ?, ?)
            ''', (name, grade, qty, json.dumps(criteria)))
        conn.commit()
        return True
    except Exception as e:
        print(f"DB Error: {e}")
        return False
    finally:
        conn.close()

# --- [MỚI] HÀM XÓA ---
def delete_customer_order(order_id):
    conn = get_connection()
    try:
        conn.execute("DELETE FROM customer_orders WHERE id = ?", (order_id,))
        conn.commit()
        return True
    except Exception as e:
        print(f"Delete Error: {e}")
        return False
    finally:
        conn.close()
# Trong file db.py

def init_audit_log():
    """
    Tự động tạo bảng audit_log nếu chưa tồn tại.
    """
    conn = get_connection()
    try:
        sql_create_table = """
        CREATE TABLE IF NOT EXISTS audit_log (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            coil_id TEXT,
            user_name TEXT,
            defect_key TEXT,
            old_value REAL,
            new_value REAL,
            changed_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        );
        """
        conn.execute(sql_create_table)
        conn.commit()
        print("✅ Đã kiểm tra/khởi tạo bảng audit_log thành công.")
    except Exception as e:
        print(f"❌ Lỗi khi khởi tạo audit_log: {e}")
    finally:
        conn.close()
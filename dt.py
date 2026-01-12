# update_db.py
import sqlite3

DB_FILE = 'qc_database.db'

def add_missing_table():
    conn = sqlite3.connect(DB_FILE)
    c = conn.cursor()
    
    print("Đang thêm bảng customer_orders...")
    try:
        c.execute('''
            CREATE TABLE IF NOT EXISTS customer_orders (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                customer_name TEXT,
                grade TEXT,
                qty_req INTEGER,
                priority INTEGER DEFAULT 1,
                criteria_json TEXT,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            );
        ''')
        conn.commit()
        print("✅ Thành công!")
    except Exception as e:
        print(f"❌ Lỗi: {e}")
    finally:
        conn.close()

if __name__ == "__main__":
    add_missing_table()
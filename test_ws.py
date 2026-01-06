import sqlite3
import os
from datetime import datetime

DB_NAME = 'qc_database.db' 

def get_connection():
    conn = sqlite3.connect(DB_NAME)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON") # Bắt buộc
    return conn

def migrate():
    conn = get_connection()
    cursor = conn.cursor()
    print("🚀 Bắt đầu cấu trúc lại Database (Schema tối ưu)...")

    try:
        # ========================================================
        # 1. CLEANUP
        # ========================================================
        cursor.execute("DROP TABLE IF EXISTS so_details")
        cursor.execute("DROP TABLE IF EXISTS sales_orders")
        cursor.execute("DROP TABLE IF EXISTS tdc_master")
        
        # Backup dữ liệu cũ nếu chưa backup
        cursor.execute("SELECT name FROM sqlite_master WHERE type='table' AND name='customer_orders'")
        if cursor.fetchone():
            cursor.execute("DROP TABLE IF EXISTS customer_orders_backup")
            cursor.execute("ALTER TABLE customer_orders RENAME TO customer_orders_backup")

        # ========================================================
        # 2. TẠO BẢNG (SCHEMA MỚI - LOGIC 1-N)
        # ========================================================
        
        # Bảng 1: TDC (Thư viện chuẩn) - Gắn với Khách hàng & Mác thép
        print("🛠️ Tạo bảng 'tdc_master'...")
        cursor.execute("""
            CREATE TABLE tdc_master (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                tdc_code TEXT UNIQUE, -- Mã quản lý nội bộ (VD: TDC-HSG-SAE1006-01)
                customer_name TEXT,   -- Khách hàng
                grade TEXT,           -- Mác thép
                usage_purpose TEXT,
                criteria_json TEXT DEFAULT '{}',
                created_at TEXT DEFAULT CURRENT_TIMESTAMP
            )
        """)

        # Bảng 2: Sales Order HEADER (Đại diện tờ đơn hàng)
        # Logic: 1 SO thuộc về 1 Khách hàng
        print("🛠️ Tạo bảng 'sales_orders'...")
        cursor.execute("""
            CREATE TABLE sales_orders (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                so_number TEXT UNIQUE, -- Số SO trên giấy tờ
                customer_name TEXT,    -- Tên khách hàng (Redundant nhưng tiện lợi truy vấn)
                order_date TEXT,
                status TEXT DEFAULT 'OPEN',
                created_at TEXT DEFAULT CURRENT_TIMESTAMP
            )
        """)

        # Bảng 3: Sales Order DETAILS (Chi tiết từng dòng)
        # Logic: 1 Dòng có quy cách riêng và theo 1 chuẩn TDC riêng
        print("🛠️ Tạo bảng 'so_details'...")
        cursor.execute("""
            CREATE TABLE so_details (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                so_id INTEGER,         -- Thuộc SO nào?
                tdc_id INTEGER,        -- Theo chuẩn TDC nào?
                thick REAL,            -- Dày
                width REAL,            -- Rộng
                min_weight REAL,       -- Min cuộn
                max_weight REAL,       -- Max cuộn
                qty INTEGER,           -- Số lượng cuộn
                total_weight REAL,     -- Tổng tấn
                FOREIGN KEY(so_id) REFERENCES sales_orders(id) ON DELETE CASCADE,
                FOREIGN KEY(tdc_id) REFERENCES tdc_master(id)
            )
        """)

        # ========================================================
        # 3. MIGRATE DATA (Xử lý thông minh)
        # ========================================================
        print("🔄 Đang chuyển đổi dữ liệu...")
        cursor.execute("SELECT * FROM customer_orders_backup")
        old_rows = cursor.fetchall()

        # Cache để tránh query DB nhiều lần
        # Cache SO: { 'SO-CODE': so_id }
        so_cache = {} 
        # Cache TDC: { 'CUST_NAME|GRADE': tdc_id } -> Để gom nhóm các dòng cùng Mác cùng Khách vào 1 TDC
        tdc_cache = {}

        for row in old_rows:
            # Lấy dữ liệu thô
            cust = row['customer_name']
            grade = row['grade']
            so_num = row['so_number'] if row['so_number'] and str(row['so_number']).strip() else f"NO-SO-{row['id']}"
            
            # --- BƯỚC A: XỬ LÝ TDC (Gom nhóm) ---
            # Nếu cùng Khách + Cùng Mác -> Dùng chung 1 ID TDC (Không tạo mới liên tục)
            tdc_key = f"{cust}|{grade}"
            tdc_id = None
            
            if tdc_key in tdc_cache:
                tdc_id = tdc_cache[tdc_key]
            else:
                # Tạo TDC Mới
                tdc_code = f"TDC-{cust[:3].upper()}-{grade}-{row['id']}"
                cursor.execute("""
                    INSERT INTO tdc_master (tdc_code, customer_name, grade, criteria_json, usage_purpose)
                    VALUES (?, ?, ?, ?, ?)
                """, (tdc_code, cust, grade, row['criteria_json'], "Migrated"))
                tdc_id = cursor.lastrowid
                tdc_cache[tdc_key] = tdc_id

            # --- BƯỚC B: XỬ LÝ SO HEADER (Gom nhóm) ---
            # Nếu cùng số SO -> Dùng chung 1 Header
            so_id = None
            if so_num in so_cache:
                so_id = so_cache[so_num]
            else:
                # Tạo SO Header Mới
                cursor.execute("""
                    INSERT INTO sales_orders (so_number, customer_name, order_date)
                    VALUES (?, ?, ?)
                """, (so_num, cust, datetime.now().strftime("%Y-%m-%d")))
                so_id = cursor.lastrowid
                so_cache[so_num] = so_id

            # --- BƯỚC C: TẠO DETAIL ---
            # Luôn insert dòng chi tiết, link vào SO và TDC đã tìm được ở trên
            cursor.execute("""
                INSERT INTO so_details (so_id, tdc_id, thick, width, min_weight, max_weight, qty, total_weight)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?)
            """, (so_id, tdc_id, row['target_thick'], row['target_width'], row['min_weight'], row['max_weight'], row['qty_req'], row['req_weight_total']))

        conn.commit()
        print(f"✅ HOÀN TẤT! Tạo {len(tdc_cache)} TDC, {len(so_cache)} Đơn hàng từ {len(old_rows)} dòng dữ liệu cũ.")

    except Exception as e:
        conn.rollback()
        import traceback
        traceback.print_exc()
        print(f"❌ Lỗi: {e}")
    finally:
        conn.close()

if __name__ == "__main__":
    migrate()
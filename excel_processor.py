import pandas as pd
import re
import unicodedata

# ==========================================
# 1. CÁC HÀM TIỀN XỬ LÝ (TRANSFORM)
# ==========================================

def normalize_usage_purpose(text):
    """Máy xay sinh tố: Xóa dấu, băm từ, xếp ABC cho Mục đích sử dụng"""
    if pd.isna(text) or str(text).strip() == '': return 'unknown'
    text = str(text).lower()
    text = unicodedata.normalize('NFKD', text).encode('ASCII', 'ignore').decode('utf-8')
    text = re.sub(r'[^a-z0-9]', ' ', text)
    words = text.split()
    words.sort()
    return '_'.join(words)

def make_match_key(cust, grade, purp):
    """Tạo chìa khóa siêu bọc thép: Ép liền chữ, bỏ mọi dấu cách và ký tự ẩn"""
    def clean_str(t):
        if pd.isna(t) or str(t).strip() == '': return 'unknown'
        s = str(t).lower()
        s = unicodedata.normalize('NFKD', s).encode('ASCII', 'ignore').decode('utf-8')
        s = re.sub(r'[^a-z0-9]', '', s) # Chú ý: Cắt SẠCH khoảng trắng, không để lại gì
        return s
        
    c = clean_str(cust)
    g = clean_str(grade)
    p = normalize_usage_purpose(purp) # Mục đích sử dụng dùng máy xay sinh tố
    
    return f"{c}_{g}_{p}"

def parse_coil_weight(cw_str):
    if pd.isna(cw_str) or str(cw_str).strip() == '': return 0, 0
    cw_str = str(cw_str).upper().strip()
    numbers = [float(x) for x in re.findall(r'\d+(?:\.\d+)?', cw_str)]
    if not numbers: return 0, 0
    if 'MAX' in cw_str: return 0, numbers[0] * 1000
    elif len(numbers) >= 2: return numbers[0] * 1000, numbers[1] * 1000
    elif len(numbers) == 1: return 0, numbers[0] * 1000
    return 0, 0

def safe_float(value):
    try:
        if pd.isna(value) or str(value).strip() == '': return 0.0
        clean_str = str(value).replace(',', '').strip()
        return float(clean_str)
    except Exception:
        return 0.0

# ==========================================
# 2. TỪ ĐIỂN ÁNH XẠ (MAPPING DICTIONARY)
# ==========================================
STANDARD_COLS = [
    'so_number', 'material_code', 'description', 'grade', 
    'thickness', 'width', 'total_weight', 'min_weight', 'max_weight', 'usage_purpose', 'norm_purpose'
]

EXCEL_MAPPING = {
    'HRC1': {'SO Mapping': 'so_number', 'MVT\nHRC': 'material_code', 'Material description': 'description', 'Mác thép': 'grade', 'Độ dày': 'thickness', 'Khổ rộng': 'width', 'Tổng LSX': 'total_weight', 'CW': 'raw_cw', 'Mục đích sử dụng': 'usage_purpose','NOTE MÁC ĐẶC BIỆT\nYÊU CẦU KHÁC': 'note'},
    'HRC2': {'SO Mapping': 'so_number', 'MVT\nMDD': 'material_code', 'Material Description': 'description', 'Mác thép': 'grade', 'Độ dày': 'thickness', 'Khổ rộng': 'width', 'Tổng LSX': 'total_weight', 'CW': 'raw_cw', 'Mục đích sử dụng': 'usage_purpose', 'Yêu cầu đặc biệt': 'note'}
}

# ==========================================
# 3. HÀM CHÍNH ĐỂ CHẠY (ETL PIPELINE)
# ==========================================

def process_sales_order_excel(file_path):
    xls = pd.ExcelFile(file_path)
    sheet_names = xls.sheet_names
    
    df = None
    factory_type = None
    
    if 'ĐƠN HÀNG HRC' in sheet_names:
        df = pd.read_excel(xls, sheet_name='ĐƠN HÀNG HRC')
        factory_type = 'HRC2'
    elif 'ĐƠN HÀNG' in sheet_names:
        df = pd.read_excel(xls, sheet_name='ĐƠN HÀNG')
        factory_type = 'HRC1'
    else:
        df = pd.read_excel(xls, sheet_name=0)
        
    df.columns = df.columns.astype(str).str.strip()
    raw_columns = df.columns.tolist()
    
    if factory_type is None:
        if 'MVT\nHRC' in raw_columns or 'MVT HRC' in raw_columns: factory_type = 'HRC1'
        elif 'MVT\nMDD' in raw_columns or 'MVT MDD' in raw_columns: factory_type = 'HRC2'
        else: raise ValueError(f"Không nhận diện được form Excel! Các Sheet có sẵn: {sheet_names}")

    if factory_type == 'HRC1' and 'MVT HRC' in raw_columns: df.rename(columns={'MVT HRC': 'MVT\nHRC'}, inplace=True) 
    elif factory_type == 'HRC2' and 'MVT MDD' in raw_columns: df.rename(columns={'MVT MDD': 'MVT\nMDD'}, inplace=True)

    df_standard = df.rename(columns=EXCEL_MAPPING[factory_type])
    if 'so_number' not in df_standard.columns: raise ValueError(f"Lỗi: Không tìm thấy cột SO Number")
    df_standard = df_standard.dropna(subset=['so_number'])
    
    records = df_standard.to_dict('records')
    cleaned_records = []
    
    for row in records:
        raw_so = str(row.get('so_number', '')).strip()
        if raw_so.endswith('.0'): raw_so = raw_so[:-2]
        if not raw_so.isdigit(): continue
        
        raw_mat = str(row.get('material_code', '')).strip()
        if raw_mat.endswith('.0'): raw_mat = raw_mat[:-2]
        
        min_w, max_w = parse_coil_weight(row.get('raw_cw'))
        norm_purpose = normalize_usage_purpose(row.get('usage_purpose'))
        def safe_str_to_null(val):
            if pd.isna(val) or str(val).strip() == '' or str(val).strip().lower() == 'nan':
                return None # Trả về None để pyodbc tự động convert thành NULL trong SQL
            return str(val).strip()
        clean_row = {
            'so_number': raw_so,
            'material_code': raw_mat, 
            'description': str(row.get('description', '')).strip(),
            'grade': str(row.get('grade')).strip(),
            'thickness': safe_float(row.get('thickness')),
            'width': safe_float(row.get('width')),
            'total_weight': safe_float(row.get('total_weight')) * 1000,
            'min_weight': min_w,
            'max_weight': max_w,
            'usage_purpose': str(row.get('usage_purpose', '')).strip(), 
            'norm_purpose': norm_purpose ,
            'note': safe_str_to_null(row.get('note'))
        }
        cleaned_records.append(clean_row)
        
    return cleaned_records

def sync_excel_to_database(cleaned_records, db_connection):
    cursor = db_connection.cursor()
    import datetime
    now_str = datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    
    # 1. LẤY TỪ ĐIỂN TDC HIỆN TẠI (Áp dụng bộ lọc siêu chuẩn hóa)
    cursor.execute("""
        SELECT m.id, m.customer_name, m.grade, m.usage_purpose 
        FROM tdc_master m
        JOIN tdc_versions v ON m.id = v.master_id
        WHERE v.status = 'Active'
    """)
    tdc_dict = {}
    for r in cursor.fetchall():
        key = make_match_key(r[1], r[2], r[3])
        tdc_dict[key] = r[0] 

    # 2. LẤY DANH SÁCH KHÁCH HÀNG TỪ SAP
    cursor.execute("""
        SELECT [Sales Document], MAX([Customer]) 
        FROM [factory].[dbo].[so] WITH(NOLOCK) 
        GROUP BY [Sales Document]
    """)
    sap_customer_dict = {str(r[0]).strip(): str(r[1]).strip() for r in cursor.fetchall()}

    # 3. LẤY DỮ LIỆU CŨ TỪ DB
    cursor.execute("SELECT so_number, material_code, tdc_id FROM so_details")
    existing_so_dict = {f"{str(r[0]).strip().upper()}_{str(r[1]).strip().upper()}": r[2] for r in cursor.fetchall()}

    cursor.execute("SELECT so_number FROM sales_orders")
    existing_headers = set(str(r[0]).strip().upper() for r in cursor.fetchall())

    # 4. ĐỒNG BỘ
    insert_count = update_count = 0

    for row in cleaned_records:
        so_num = str(row['so_number']).strip()
        mat_code = str(row['material_code']).strip()
        so_num_upper = so_num.upper()
        mat_code_upper = mat_code.upper()
        so_mat_key = f"{so_num_upper}_{mat_code_upper}"
        
        excel_cust = str(row.get('customer_name', '')).strip()
        cust = sap_customer_dict.get(so_num, excel_cust) 
        
        grade = str(row.get('grade', ''))
        purp = row.get('usage_purpose', '')
        
        # Xử lý Header
        if so_num_upper not in existing_headers:
            try:
                cursor.execute("""
                    INSERT INTO sales_orders (so_number, customer_name, created_at, status)
                    VALUES (?, ?, ?, 'Pending')
                """, (so_num, cust, now_str))
                existing_headers.add(so_num_upper)
            except Exception: pass

        # TẠO CHÌA KHÓA TRA CỨU
        lookup_key = make_match_key(cust, grade, purp)
        suggested_tdc_id = tdc_dict.get(lookup_key, None) 

        # Xử lý Details
        if so_mat_key in existing_so_dict:
            current_db_tdc = existing_so_dict[so_mat_key]
            final_tdc_id = current_db_tdc if current_db_tdc else suggested_tdc_id

            cursor.execute("""
                UPDATE so_details
                SET 
                    description = CASE WHEN description IS NULL OR LTRIM(RTRIM(description)) = '' THEN ? ELSE description END,
                    grade = CASE WHEN grade IS NULL OR LTRIM(RTRIM(grade)) = '' THEN ? ELSE grade END,
                    thickness = CASE WHEN thickness IS NULL OR thickness = 0 THEN ? ELSE thickness END,
                    width = CASE WHEN width IS NULL OR width = 0 THEN ? ELSE width END,
                    total_weight = CASE WHEN total_weight IS NULL OR total_weight = 0 THEN ? ELSE total_weight END,
                    min_weight = CASE WHEN min_weight IS NULL OR min_weight = 0 THEN ? ELSE min_weight END,
                    max_weight = CASE WHEN max_weight IS NULL OR max_weight = 0 THEN ? ELSE max_weight END,
                    usage_purpose = CASE WHEN usage_purpose IS NULL OR LTRIM(RTRIM(usage_purpose)) = '' THEN ? ELSE usage_purpose END,
                    note = CASE WHEN note IS NULL OR LTRIM(RTRIM(note)) = '' THEN ? ELSE note END,
                    tdc_id = CASE WHEN tdc_id IS NULL THEN ? ELSE tdc_id END
                WHERE so_number = ? AND LTRIM(RTRIM(material_code)) = ?
            """, (
                row['description'], row['grade'], row['thickness'], row['width'],
                row['total_weight'], row['min_weight'], row['max_weight'], 
                row['usage_purpose'], 
                row['note'], # <--- TRUYỀN NOTE VÀO
                final_tdc_id, so_num, mat_code
            ))
            update_count += 1
        else:
            try:
                cursor.execute("""
                    INSERT INTO so_details (
                        so_number, material_code, description, grade, 
                        thickness, width, total_weight, min_weight, max_weight, 
                        usage_purpose, note, tdc_id, status
                    ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, 'Hidden')
                """, (
                    so_num, mat_code, row['description'], row['grade'],
                    row['thickness'], row['width'], row['total_weight'], 
                    row['min_weight'], row['max_weight'], row['usage_purpose'],
                    row['note'], # <--- TRUYỀN NOTE VÀO (Lưu ý: giữ status 'Hidden')
                    suggested_tdc_id 
                ))
                existing_so_dict[so_mat_key] = suggested_tdc_id 
                insert_count += 1
            except Exception as e: 
                print(f"Lỗi Insert: {e}")

    db_connection.commit()
    return insert_count, update_count
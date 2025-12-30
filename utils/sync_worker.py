from flask import Blueprint, app, render_template, current_app, request, jsonify
import pandas as pd
import threading
import json
import db  # Module db.py
import requests
from apscheduler.schedulers.background import BackgroundScheduler
from datetime import datetime 
import requests
import pymysql 
from utils.common import sanitize_data
from utils.scoring import process_coil_scores
from utils.constants import DEFAULT_CONFIG_TEMPLATE
from apscheduler.schedulers.background import BackgroundScheduler
import time
import websocket


upload_lock = threading.Lock()
# =======================================================
API_GEOMETRY_BATCH_URL = "http://10.192.49.39:5026/hsm" 
# URL lấy lẻ 1 cuộn - Dùng cho Manual Scan
API_GEO_SINGLE_URL = "http://10.192.49.39:5026/hsm?piece_id=" 
# wes socket 
WS_URL = "ws://10.192.49.39:8001/ws"
# URL Surface
API_SURFACE_URL = "http://10.192.49.39:5025/defects"
VIEW_TPHH = "view_dq1_nmlt_nuocthep"
VIEW_CO_TINH = "view_dq1_nmhrc1_cotinh"         
# Cấu hình tên cột trong MySQL 
COL_ID_CUON = "SampleName"     
COL_ID_PHOI_COTINH = "BilletLotName"   
COL_ID_PHOI_TPHH = "BilletLotCode" 
LAST_DATA_UPDATE = {
    'timestamp': time.time(),
    'message': ''
}
processing_coils = set() # Set chống trùng lặp

# =======================================================
# PHẦN 1: API CHO FRONTEND KIỂM TRA UPDATE
# =======================================================

def notify_frontend(msg, title="Cập nhật dữ liệu"):
    """Hàm cập nhật trạng thái: Vừa báo Web, Vừa lưu DB"""
    global LAST_DATA_UPDATE
    from routes.dashboard import log_system_event
    LAST_DATA_UPDATE['timestamp'] = time.time()
    LAST_DATA_UPDATE['message'] = f"{title}: {msg}"
    
    # 2. Lưu vào Database (Lịch sử)
    try:
        log_system_event(title, msg, 'success')
    except:
        pass # Tránh crash luồng chính nếu lỗi DB
    
    print(f"📢 [NOTIFY] {title}: {msg}")
# =======================================================
# PHẦN 2: WEBSOCKET CLIENT (REALTIME)
# =======================================================
def is_coil_in_db(coil_id):
    try:
        conn = db.get_connection()
        row = conn.execute("SELECT 1 FROM coil_data WHERE coil_id = ?", (coil_id,)).fetchone()
        conn.close()
        return row is not None
    except: return False

def on_ws_message(ws, message):
    global processing_coils
    try:
        response = json.loads(message)
        final_coil_id = None
        
        # Lấy ID từ Cam43Marktxt
        if isinstance(response, dict):
            data = response.get('data', {})
            final_coil_id = data.get('Cam43Marktxt') or data.get('MarkingText') or data.get('CoilID')

        if final_coil_id:
            final_coil_id = str(final_coil_id).strip()
            
            # Lọc trùng lặp
            if final_coil_id in processing_coils: return
            if is_coil_in_db(final_coil_id): return

            print(f"⚡ [WebSocket] ID Mới: {final_coil_id}")
            processing_coils.add(final_coil_id)
            
            # Chạy ngay lập tức (Không chờ)
            threading.Thread(target=run_immediate_sync, args=(final_coil_id,)).start()
            
    except Exception as e:
        print(f"⚠️ WS Parse Error: {e}")


def on_ws_error(ws, error): print(f"❌ [WS Error] {error}")
def on_ws_close(ws, status, msg):
    print("🔌 [WS] Closed. Reconnecting in 5s...")
    time.sleep(5)
    start_websocket_listener()

def start_websocket_listener():
    def run():
        # Header giả lập Chrome
        headers = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) Chrome/120.0.0.0 Safari/537.36"}
        websocket.enableTrace(False)
        ws = websocket.WebSocketApp(WS_URL, on_message=on_ws_message, on_error=on_ws_error, on_close=on_ws_close, header=headers)
        ws.run_forever()
    threading.Thread(target=run, daemon=True).start()
# =======================================================
# PHẦN 3: CÁC HÀM ĐỒNG BỘ DỮ LIỆU TỪ NGOÀI
def process_and_save_geometry(data_rows):
    """
    Hàm core: Nhận list data từ API Geometry -> Map dữ liệu -> Lưu DB
    [UPDATE]: Ghi đè Raw Data + Bảo vệ điểm số nếu đã chốt tay (is_checked=1)
    """
    processed_ids = []
    batch_data = []
    
    conn = db.get_connection()
    # [SỬA 1]: Lấy thêm cột scores và is_checked
    existing_rows = conn.execute("SELECT coil_id, raw_data, grade, scores, is_checked FROM coil_data").fetchall()
    conn.close()
    
    # [SỬA 2]: Map thêm thông tin scores và is_checked
    existing_map = {r['coil_id']: {
        'raw': json.loads(r['raw_data']) if r['raw_data'] else {}, 
        'grade': r['grade'],
        'scores': json.loads(r['scores']) if r['scores'] else {},
        'is_checked': r['is_checked']
    } for r in existing_rows}

    for row in data_rows:
        if 'debug_printed' not in globals():
            print("\n--- API KEYS DEBUG ---")
            print(row.keys()) # In ra danh sách tên trường
            # print(row)      # Hoặc in cả dòng nếu cần xem giá trị
            print("----------------------\n")
            globals()['debug_printed'] = True
        r_id = row.get('TASK_SLAB') or row.get('piece_id') or row.get('COIL_ID') or row.get('SLAB_ID')
        if not r_id: continue
        coil_id = str(r_id).strip().upper()

        raw_map = {}
        # ... (Phần mapping dữ liệu Crown, Wedge, Flatness giữ nguyên như code cũ) ...
        if row.get('AVG_CROWN') is not None: raw_map['Crown'] = float(row.get('AVG_CROWN'))
        if row.get('AVG_WEDGE') is not None: raw_map['Wedge'] = float(row.get('AVG_WEDGE'))
        if row.get('FLATNEES') is not None: raw_map['Flatness'] = float(row.get('FLATNEES')) 
        
        tgt_thick = pd.to_numeric(row.get('TARGTHK') or row.get('TARGET_THICK'), errors='coerce')
        act_thick = pd.to_numeric(row.get('THICK'), errors='coerce') 
        if pd.notnull(act_thick) and pd.notnull(tgt_thick):
            raw_map['ThickDiff'] = abs(act_thick - tgt_thick)

        # 2. Rộng mục tiêu
        tgt_width = pd.to_numeric(row.get('TARGWIDTH') or row.get('TARGET_WIDTH'), errors='coerce')
        act_width = pd.to_numeric(row.get('WIDTH'), errors='coerce')
        if pd.notnull(act_width) and pd.notnull(tgt_width):
            raw_map['WidthDiff'] = abs(act_width - tgt_width)

        # 3. Khối lượng (Cần check kỹ key của API trả về, thường là WEIGHT, COIL_WEIGHT, hoặc MASS)
        raw_weight = row.get('KhoiLuongPDI') or row.get('COIL_WEIGHT')
        if isinstance(raw_weight, str):
            raw_weight = raw_weight.replace(',', '') # Xóa dấu phẩy
        
        weight_val = pd.to_numeric(raw_weight, errors='coerce')
        
        clean_raw = sanitize_data(raw_map)
        
        # Kiểm tra dữ liệu rỗng
        has_weight = pd.notnull(weight_val) and weight_val > 0
        
        # Chỉ bỏ qua khi: Không có thông số hình học VÀ Không có khối lượng
        if not clean_raw and not has_weight: 
            continue

        # Lấy thông tin hiện tại (hoặc tạo mới)
        # Mặc định is_checked = 0
        current_info = existing_map.get(coil_id, {'raw': {}, 'grade': 'SAE1006', 'scores': {}, 'is_checked': 0})
        
        final_grade = current_info['grade']
        api_grade = str(row.get('STEEL_GRADE', '')).strip().upper()
        if final_grade == 'SAE1006' and api_grade and api_grade not in ['NONE', '', 'NULL']:
            final_grade = api_grade

        # --- LOGIC QUAN TRỌNG: MERGE DATA ---
        full_raw = current_info['raw'].copy()
        full_raw.update(clean_raw) # Ghi đè dữ liệu mới vào
        
        # Tính điểm tự động (luôn tính để tham khảo hoặc dùng nếu chưa chốt)
        new_auto_scores = process_coil_scores(coil_id, full_raw, final_grade)
        
        # --- LOGIC QUAN TRỌNG: QUYẾT ĐỊNH ĐIỂM SỐ ---
        final_scores = new_auto_scores # Mặc định lấy điểm máy
        
        # Nếu đã sửa tay (is_checked == 1) -> Giữ nguyên điểm cũ
        if current_info.get('is_checked') == 1:
            final_scores = current_info['scores']
        batch_data.append({
            'id': coil_id, 
            'grade': final_grade, 
            'raw': full_raw, 
            'scores': final_scores,
            'is_checked': current_info.get('is_checked', 0),
            # [MỚI] Thêm 3 trường này vào dict để lưu
            'weight': float(weight_val) if pd.notnull(weight_val) else 0,
            'target_thick': float(tgt_thick) if pd.notnull(tgt_thick) else 0,
            'target_width': float(tgt_width) if pd.notnull(tgt_width) else 0
        })
        processed_ids.append(coil_id)

    if batch_data:
        db.save_batch_coils_v2(batch_data)
        
    return processed_ids
def sync_geometry_api():
    """BƯỚC 1: Quét Geometry Batch -> Lưu DB -> Return List IDs"""
    print(f"🔄 [Geometry] Bắt đầu quét lúc {datetime.now().strftime('%H:%M:%S')}...")
    try:
        resp = requests.get(API_GEOMETRY_BATCH_URL, timeout=10)
        json_data = resp.json()
        rows = []
        if isinstance(json_data, list):
            rows = json_data
        elif isinstance(json_data, dict):
            rows = json_data.get('data') or json_data.get('rows') or json_data.get('result') or []
            
        if not rows:
            print("💤 [Geometry] API trả về rỗng.")
            return []

        new_ids = process_and_save_geometry(rows)
        print(f"✅ [Geometry] Đã cập nhật {len(new_ids)} cuộn.")
        return new_ids

    except Exception as e:
        print(f"❌ [Geometry Error] {e}")
        return []
#sync surface defects from external API

def sync_surface_defects(target_ids=None):

    with upload_lock:
        if not target_ids: return 0

        print(f"🔄 [Surface] Bắt đầu quét {len(target_ids)} cuộn...")
        
        conn = db.get_connection()
        placeholders = ','.join('?' * len(target_ids))
        query = f"SELECT coil_id, raw_data, grade, scores, is_checked FROM coil_data WHERE coil_id IN ({placeholders})"
        existing_rows = conn.execute(query, target_ids).fetchall()
        conn.close()

        existing_map = {r['coil_id']: {
            'raw': json.loads(r['raw_data']) if r['raw_data'] else {}, 
            'grade': r['grade'],
            'scores': json.loads(r['scores']) if r['scores'] else {},
            'is_checked': r['is_checked']
        } for r in existing_rows}

        batch_save = []
        whitelist = DEFAULT_CONFIG_TEMPLATE.get('SAE1006', {}).keys()

        for coil_id in target_ids:
            try:
                url = f"{API_SURFACE_URL}?customer_id={coil_id}"
                resp = requests.get(url, timeout=5)
                if resp.status_code != 200: continue
                data = resp.json()
                raw_rows = data.get('rows', [])
                if not raw_rows: continue
    
                coil_defects = {}
                for row in raw_rows:
                    defect = str(row.get('DefectClass')).strip()
                    if defect not in whitelist: continue
                    try: val = float(row.get('Size'))
                    except: val = 0.0
                    if defect not in coil_defects: coil_defects[defect] = []
                    coil_defects[defect].append(val)
                
                # --- LOGIC XỬ LÝ ---
                curr = existing_map.get(coil_id, {'raw': {}, 'grade': 'SAE1006', 'scores': {}, 'is_checked': 0})
                
                final_raw = curr['raw'].copy()
                final_raw.update(coil_defects) # Ghi đè list lỗi mới
                clean_raw = sanitize_data(final_raw)
                
                new_auto_scores = process_coil_scores(coil_id, clean_raw, curr['grade'])
                
                # Bảo vệ điểm
                final_scores = new_auto_scores
                if curr.get('is_checked') == 1:
                    final_scores = curr['scores']
                
                batch_save.append({
                    'id': coil_id, 'grade': curr['grade'], 'raw': clean_raw, 
                    'scores': final_scores, 
                    'is_checked': curr.get('is_checked', 0)
                })
            except: continue

        count_updated = 0
        if batch_save:
            db.save_batch_coils(batch_save)
            count_updated = len(batch_save)
            print(f"✅ [Surface] Đã đồng bộ {count_updated} cuộn.")
            
        return count_updated
MYSQL_CONFIG = {
    'host': '10.192.215.11',  # VD: 192.168.1.xxx
    'user': 'viewkcs',
    'password': 'viewkcs@2024',
    'database': 'bkmis_kcshpsdq',
    'port': 3307
}

#sync mechanical & chemical properties from MySQL
# Trong file sync_worker.py

def sync_properties_mysql(target_ids=None):
    if not target_ids: return 0

    CHUNK_SIZE = 1000  # Mỗi lần chỉ gửi 1000 ID sang MySQL
    total_updated = 0
    
    # Vòng lặp xử lý từng gói nhỏ
    for i in range(0, len(target_ids), CHUNK_SIZE):
        chunk_ids = target_ids[i : i + CHUNK_SIZE]
        print(f"🧪 [Properties] Đang xử lý gói {i//CHUNK_SIZE + 1}: {len(chunk_ids)} cuộn...")
        
        # --- BẮT ĐẦU LOGIC CŨ (Đã thụt lề vào trong vòng lặp) ---
        ids_str = ",".join([f"'{str(x)}'" for x in chunk_ids])
        final_data_map = {} 
        slab_to_coils_map = {}

        try:
            conn_mysql = pymysql.connect(**MYSQL_CONFIG, cursorclass=pymysql.cursors.DictCursor)
            with conn_mysql.cursor() as cursor:
                # 1. Cơ tính
                sql_cotinh = f"""
                    SELECT * FROM {VIEW_CO_TINH} 
                    WHERE SUBSTRING_INDEX({COL_ID_CUON}, '/', 1) IN ({ids_str})
                """
                cursor.execute(sql_cotinh)
                rows_cotinh = cursor.fetchall()
                target_slabs = set() 

                for r in rows_cotinh:
                    raw_coil_id = str(r[COL_ID_CUON])
                    coil_id = raw_coil_id.split('/')[0].strip().upper()
                    if coil_id not in final_data_map: final_data_map[coil_id] = {}

                    if r.get('Yeild') is not None: final_data_map[coil_id]['YieldPoint'] = float(r['Yeild'])
                    if r.get('Tensile') is not None: final_data_map[coil_id]['Tensile'] = float(r['Tensile'])
                    if r.get('Elongation') is not None: final_data_map[coil_id]['Elongation'] = float(r['Elongation'])
                    if r.get('HRB') is not None: final_data_map[coil_id]['Hardness'] = float(r['HRB'])

                    slab_id = r.get(COL_ID_PHOI_COTINH)
                    if slab_id:
                        slab_id = str(slab_id).strip()
                        target_slabs.add(slab_id)
                        if slab_id not in slab_to_coils_map: slab_to_coils_map[slab_id] = []
                        slab_to_coils_map[slab_id].append(coil_id)

                # 2. TPHH
                if target_slabs:
                    slabs_str = ",".join([f"'{str(x)}'" for x in target_slabs])
                    sql_tphh = f"SELECT * FROM {VIEW_TPHH} WHERE {COL_ID_PHOI_TPHH} IN ({slabs_str})"
                    cursor.execute(sql_tphh)
                    rows_tphh = cursor.fetchall()

                    for r in rows_tphh:
                        slab_id = str(r.get(COL_ID_PHOI_TPHH)).strip()
                        associated_coils = slab_to_coils_map.get(slab_id, [])
                        for coil_id in associated_coils:
                            if r.get('C') is not None: final_data_map[coil_id]['C'] = float(r['C'])
                            if r.get('Mn') is not None: final_data_map[coil_id]['Mn'] = float(r['Mn'])
                            if r.get('Si') is not None: final_data_map[coil_id]['Si'] = float(r['Si'])
                            if r.get('P') is not None: final_data_map[coil_id]['P'] = float(r['P'])
                            if r.get('S') is not None: final_data_map[coil_id]['S'] = float(r['S'])
            conn_mysql.close()
            
            # LƯU VÀO DB LOCAL (Cho từng gói)
            if final_data_map: 
                batch_save = []
                conn_local = db.get_connection()
                clean_ids_found = list(final_data_map.keys())
                placeholders = ','.join('?' * len(clean_ids_found))
                query = f"SELECT coil_id, raw_data, grade, scores, is_checked FROM coil_data WHERE coil_id IN ({placeholders})"
                existing_rows = conn_local.execute(query, clean_ids_found).fetchall()
                conn_local.close()

                existing_map = {r['coil_id']: {
                    'raw': json.loads(r['raw_data']) if r['raw_data'] else {}, 
                    'grade': r['grade'],
                    'scores': json.loads(r['scores']) if r['scores'] else {},
                    'is_checked': r['is_checked']
                } for r in existing_rows}

                for cid, new_props in final_data_map.items():
                    curr = existing_map.get(cid, {'raw': {}, 'grade': 'SAE1006', 'scores': {}, 'is_checked': 0})
                    final_raw = curr['raw'].copy()
                    final_raw.update(new_props)
                    clean_raw = sanitize_data(final_raw)
                    new_auto_scores = process_coil_scores(cid, clean_raw, curr['grade'])
                    
                    final_scores = new_auto_scores
                    if curr.get('is_checked') == 1: final_scores = curr['scores']
                    
                    batch_save.append({
                        'id': cid, 'grade': curr['grade'], 'raw': clean_raw, 
                        'scores': final_scores, 'is_checked': curr.get('is_checked', 0)
                    })

                if batch_save: 
                    db.save_batch_coils(batch_save)
                    total_updated += len(batch_save)

        except Exception as e:
            print(f"❌ [Properties Error - Chunk] {str(e)}")
            continue # Nếu gói này lỗi thì bỏ qua, chạy gói tiếp theo

    return total_updated
def rescan_recent_coils_for_mechanical():
    print("\n--- 🐢 BẮT ĐẦU QUÉT BÙ CƠ TÍNH (SMART SCAN) ---")
    
    try:
        conn = db.get_connection()
        # 1. Lấy 10.000 - 20.000 cuộn gần nhất (để bao phủ thời gian 5-10 ngày)
        query = "SELECT coil_id, raw_data FROM coil_data ORDER BY rowid DESC LIMIT 15000"
        rows = conn.execute(query).fetchall()
        conn.close()
        
        if not rows:
            print("💤 Kho dữ liệu trống.")
            return

        # 2. BỘ LỌC THÔNG MINH (Filter)
        # Chỉ lấy những ID mà trong raw_data CHƯA CÓ các trường quan trọng (YieldPoint, Tensile...)
        target_ids = []
        for r in rows:
            try:
                # Parse dữ liệu hiện tại của cuộn
                raw = json.loads(r['raw_data']) if r['raw_data'] else {}
                if not raw.get('YieldPoint') or not raw.get('Tensile'):
                    target_ids.append(r['coil_id'])
            except:
                target_ids.append(r['coil_id'])

        if not target_ids:
            print(f"✅ Đã kiểm tra {len(rows)} cuộn gần nhất. Tất cả đều ĐÃ CÓ đủ cơ tính. Không cần quét.")
            return

        print(f"🔎 Phát hiện {len(target_ids)}/{len(rows)} cuộn bị thiếu Cơ tính/TPHH.")
        print(f"🚀 Tiến hành quét bù cho {len(target_ids)} cuộn này...")

        # 3. Gửi danh sách đã lọc đi quét (Hàm này đã có logic chia nhỏ Chunking nên rất an toàn)
        updated_count = sync_properties_mysql(target_ids=target_ids)
        
        if updated_count > 0:
            notify_frontend(f"Đã cập nhật bù cơ tính: {updated_count} cuộn")

    except Exception as e:
        print(f"❌ Lỗi Job Bù đắp: {str(e)}")
    
    print("--- 🏁 KẾT THÚC QUÉT BÙ ---\n")
def run_full_sync_flow():
    """Hàm chạy định kỳ 5 phút: Geo -> Surf -> Prop"""
    print("\n--- 🚀 AUTO SYNC START ---")
    
    # 1. Lấy Geometry -> Trả về list ID mới
    new_ids = sync_geometry_api() 
    
    if new_ids:
        print(f"➡️ Có {len(new_ids)} cuộn mới. Tiếp tục quét Surface & Properties...")
        
        sync_surface_defects(new_ids) 
        
        sync_properties_mysql(new_ids)
        
    else:
        print("💤 Không có cuộn mới. Kết thúc chu trình.")
        
    print("--- 🏁 AUTO SYNC END ---\n")
scheduler = BackgroundScheduler()
# Scheduler initialization
def init_scheduler():
    if not scheduler.running:
        scheduler.add_job(run_full_sync_flow, trigger="interval", minutes=5, id='master_sync_job', replace_existing=True, next_run_time=datetime.now())
        scheduler.add_job(rescan_recent_coils_for_mechanical, trigger="interval", minutes=60, id='mechanical_catchup_job', replace_existing=True, next_run_time=datetime.now() + pd.Timedelta(minutes=1))
        scheduler.start()
        
        # [MỚI] KHỞI ĐỘNG WEBSOCKET
        print("🚀 Khởi động WebSocket Listener...")
        start_websocket_listener()

def run_immediate_sync(target_id):
    global processing_coils
    try:
        details = []
        
        # 1. Surface
        cnt = sync_surface_defects([target_id])
        if cnt > 0: details.append("Bề mặt (OK)")
        else: details.append("Bề mặt (Không có)")

        # 2. Geometry
        geo_ok = False
        try:
            res = requests.get(f"{API_GEO_SINGLE_URL}{target_id}", timeout=5)
            if res.status_code == 200:
                rows = res.json()
                if isinstance(rows, dict): rows = rows.get('data', [])
                if rows: 
                    process_and_save_geometry(rows)
                    geo_ok = True
        except: pass
        
        if geo_ok: details.append("Hình học (OK)")
        else: details.append("Hình học (Lỗi/Không có)")

        # 3. Thông báo chi tiết
        final_msg = f"Cuộn {target_id} - " + ", ".join(details)
        notify_frontend(final_msg, title="Auto Sync")

    except Exception as e:
        print(f"❌ Sync Error {target_id}: {e}")
        notify_frontend(f"Lỗi quét {target_id}: {str(e)}", title="Lỗi Hệ Thống")
    finally:
        if target_id in processing_coils:
            processing_coils.remove(target_id)
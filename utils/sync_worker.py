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
notify_lock = threading.Lock()

def clean_date_sql(date_str):
    """Làm sạch ngày tháng cho SQL Server"""
    if not date_str: return None
    s = str(date_str).strip()
    if s == '' or s.lower() == 'none': return None
    
    # 1. Bỏ chữ 'T' (VD: 2025-12-31T04:10... -> 2025-12-31 04:10...)
    s = s.replace('T', ' ')
    
    # 2. Cắt bỏ mili-giây (VD: ...:27.410000 -> ...:27)
    if '.' in s: s = s.split('.')[0]
    return s
def debug_check_data(source_name, data_row):
    """
    Hàm soi dữ liệu: In ra độ dài của tất cả các trường.
    Báo động đỏ nếu trường nào dài quá 50 ký tự.
    """
    has_error = False
    for key, value in data_row.items():
        # Chuyển về chuỗi để đếm độ dài
        val_str = str(value) if value is not None else ""
        val_len = len(val_str)
        if val_len > 45 and key not in ['raw', 'scores', 'raw_data']:
            has_error = True
    
    if not has_error:
        print("   ✅ Dữ liệu an toàn.")
    else:
        print("   ❌ PHÁT HIỆN NGUY CƠ LỖI!")
COIL_COOLDOWN_CACHE = {}
API_GEO_SINGLE_URL = "http://10.192.49.39:5026/hsm?piece_id=" 
API_SURFACE_URL = "http://10.192.49.39:5025/defects" 
FACTORY_CONFIGS = {
    'HRC1': {
        'name': 'Nhà máy HRC 1',
        'api_geo': 'http://10.192.49.39:5026/hsm?piece_id=', 
        'api_surf': 'http://10.192.49.39:5025/defects?customer_id=',
        'ws_url': 'ws://10.192.49.39:8001/ws',
        'db_prop_view': 'view_dq1_nmhrc1_cotinh',
        'db_tphh_view': 'view_dq1_nmlt_nuocthep',
        'db_conn':{
                        'host': '10.192.215.11',  # VD: 192.168.1.xxx
                        'user': 'viewkcs',
                        'password': 'viewkcs@2024',
                        'database': 'bkmis_kcshpsdq',
                        'port': 3307
                    }
    },
    'HRC2': {
        'name': 'Nhà máy HRC 2',
        'api_geo': 'http://10.192.50.24:5205/api/hsm?coilId=', # IP khác
        'api_surf': 'http://10.192.50.24:5205/api/defects?coilId=',
        'ws_url': 'ws://10.192.50.24:5205/ws',
        'db_prop_view': 'view_dq2_nmhrc2_cotinh',
        'db_tphh_view': 'view_dq2_nmlt_nuocthep',
        'db_conn':{
                        'host': '10.192.215.11',  # VD: 192.168.1.xxx
                        'user': 'viewkcs',
                        'password': 'viewkcs@2024',
                        'database': 'bkmis_kcshpsdq',
                        'port': 3307
                    } # View SQL Server riêng của HRC2
    }
}    
# =======================================================
COL_ID_CUON = "SampleName"      
COL_ID_PHOI_COTINH = "BilletLotName"   
COL_ID_PHOI_TPHH = "BilletLotCode" 

LAST_NOTIFY_CACHE = {
    'message': '',
    'time': 0
}

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
    global LAST_DATA_UPDATE, LAST_NOTIFY_CACHE

    with notify_lock:
        current_time = time.time()
        full_msg = f"{title}: {msg}"
        
        # Check trùng nội dung trong vòng 60s
        if full_msg == LAST_NOTIFY_CACHE['message']:
            if (current_time - LAST_NOTIFY_CACHE['time']) < 60:
                return 

        # Cập nhật Cache ngay trong Lock
        LAST_NOTIFY_CACHE['message'] = full_msg
        LAST_NOTIFY_CACHE['time'] = current_time

        # Cập nhật biến RAM cho Frontend
        LAST_DATA_UPDATE['timestamp'] = current_time
        LAST_DATA_UPDATE['message'] = full_msg
    from routes.dashboard import log_system_event
    try:
        log_system_event(title, msg, 'success')
    except:
        pass 
# =======================================================
# PHẦN 2: WEBSOCKET CLIENT (REALTIME)
# =======================================================
def is_coil_in_db(coil_id):
    try:
        conn = db.get_connection()
        cursor = conn.cursor()
        row = cursor.execute("SELECT 1 FROM coil_data WITH (NOLOCK) WHERE coil_id = ?", (coil_id,)).fetchone()
        conn.close()
        return row is not None
    except: return False

def on_ws_message(ws, message, factory_id):
    global COIL_COOLDOWN_CACHE
    try:
        response = json.loads(message)
        final_coil_id = None

        if isinstance(response, dict):
            data = response.get('data', {})
            final_coil_id = data.get('Cam43Marktxt') or data.get('MarkingText') or data.get('CoilID')

        if final_coil_id:
            final_coil_id = str(final_coil_id).strip()
            current_ts = time.time()

            expired_keys = [k for k, v in COIL_COOLDOWN_CACHE.items() if current_ts - v > 300]
            for k in expired_keys: del COIL_COOLDOWN_CACHE[k]

            if final_coil_id in COIL_COOLDOWN_CACHE: return
            if is_coil_in_db(final_coil_id): return

            print(f"⚡ [WS - {factory_id}] ID Mới: {final_coil_id}")
            
            COIL_COOLDOWN_CACHE[final_coil_id] = current_ts

            threading.Thread(target=run_immediate_sync, args=(final_coil_id, factory_id)).start()
            
    except Exception as e:
        print(f"⚠️ WS Parse Error ({factory_id}): {e}")


def on_ws_error(ws, error): print(f"❌ [WS Error] {error}")
def on_ws_close(ws, status, msg):
    print("🔌 [WS] Closed. Reconnecting in 5s...")
    time.sleep(5)
    start_websocket_listener()

def start_websocket_listener():
    """Khởi động lắng nghe cho TẤT CẢ nhà máy trong Config"""
    
    headers = {"User-Agent": "Mozilla/5.0 ..."} # Giữ nguyên header của bạn

    for fid, cfg in FACTORY_CONFIGS.items():
        ws_url = cfg['ws_url']

        def create_on_message(f_id):
            return lambda ws, msg: on_ws_message(ws, msg, f_id)
            
        def create_on_close(f_id):
            def on_close(ws, status, msg):
                print(f"🔌 [WS - {f_id}] Closed. Reconnecting in 5s...")
                time.sleep(5)
                # Khởi động lại chỉ luồng này
                threading.Thread(target=run_single_listener, args=(f_id,), daemon=True).start()
            return on_close

        def run_single_listener(f_id):
            target_url = FACTORY_CONFIGS[f_id]['ws_url']
            ws = websocket.WebSocketApp(
                target_url,
                on_message=create_on_message(f_id),
                on_error=lambda ws, err: print(f"❌ [WS - {f_id}] Error: {err}"),
                on_close=create_on_close(f_id),
                header=headers
            )
            ws.run_forever()

        # Chạy thread riêng cho từng nhà máy
        t = threading.Thread(target=run_single_listener, args=(fid,), daemon=True)
        t.start()
# =======================================================
# [MỚI] Hàm đồng bộ TPHH dựa trên Mác phôi (Lấy từ Geometry)
def sync_tphh_from_slabs(coil_slab_map, factory_id="HRC1"):
    """
    coil_slab_map: Dict { 'COIL_ID': 'SLAB_ID', ... }
    Mục tiêu: Lấy TPHH ngay khi có Geometry mà không cần chờ Cơ tính.
    """
    if not coil_slab_map: return
    
    cfg = FACTORY_CONFIGS.get(factory_id)
    if not cfg: return

    print(f"🧪 [Early TPHH] Đang tra cứu TPHH cho {len(coil_slab_map)} cuộn từ Mác phôi...")

    current_db_conn = cfg['db_conn']
    current_view_tphh = cfg['db_tphh_view']
    
    # 1. Lấy danh sách Slab ID unique để query
    slab_ids = list(set(coil_slab_map.values()))
    slabs_str = ",".join([f"'{str(x)}'" for x in slab_ids])
    
    final_data_map = {} # Map: CoilID -> {C, Mn, Si...}

    try:
        # Kết nối MySQL lấy TPHH
        conn_mysql = pymysql.connect(**current_db_conn, cursorclass=pymysql.cursors.DictCursor)
        with conn_mysql.cursor() as cursor:
            # Query bảng TPHH
            sql_tphh = f"SELECT * FROM {current_view_tphh} WHERE {COL_ID_PHOI_TPHH} IN ({slabs_str})"
            cursor.execute(sql_tphh)
            rows_tphh = cursor.fetchall()
            
            # Map dữ liệu về lại Coil ID
            for r in rows_tphh:
                slab_id = str(r.get(COL_ID_PHOI_TPHH)).strip()
                
                # Tìm tất cả cuộn có chung Slab ID này
                for coil_id, s_id in coil_slab_map.items():
                    if s_id == slab_id:
                        if coil_id not in final_data_map: final_data_map[coil_id] = {}
                        
                        # Lấy các chất hóa học
                        if r.get('C') is not None: final_data_map[coil_id]['C'] = float(r['C'])
                        if r.get('Mn') is not None: final_data_map[coil_id]['Mn'] = float(r['Mn'])
                        if r.get('Si') is not None: final_data_map[coil_id]['Si'] = float(r['Si'])
                        if r.get('P') is not None: final_data_map[coil_id]['P'] = float(r['P'])
                        if r.get('S') is not None: final_data_map[coil_id]['S'] = float(r['S'])
        
        conn_mysql.close()

        # 2. Lưu vào Database Local (Merge với dữ liệu cũ)
        if final_data_map:
            batch_save = []
            conn_local = db.get_connection()
            
            # Lấy dữ liệu hiện tại để merge
            placeholders = ','.join('?' * len(final_data_map))
            keys = list(final_data_map.keys())
            
            query = f"""
                SELECT coil_id, raw_data, grade, scores, is_checked, 
                       weight, target_thick, target_width, production_date, slab_grade,
                       Temperature, Speed  
                FROM coil_data WITH (NOLOCK) WHERE coil_id IN ({placeholders})
            """
            cursor = conn_local.cursor()
            cursor.execute(query, keys)
            existing_rows = db.fetchall_as_dict(cursor)
            conn_local.close()
            
            existing_map = {r['coil_id']: r for r in existing_rows}

            for cid, tphh_data in final_data_map.items():
                if not tphh_data:
                        continue
                curr = existing_map.get(cid, {})
                if not curr: continue # Không update nếu cuộn chưa tồn tại (lý thuyết là đã có vì vừa chạy geo xong)

                old_raw = json.loads(curr['raw_data']) if curr.get('raw_data') else {}
                
                # Merge TPHH vào
                final_raw = old_raw.copy()
                final_raw.update(tphh_data)
                clean_raw = sanitize_data(final_raw)

                # Tính lại điểm
                curr_grade = curr.get('grade', 'SAE1006')
                new_auto_scores = process_coil_scores(cid, clean_raw, curr_grade)

                # Bảo vệ điểm tay
                final_scores = new_auto_scores
                if curr.get('is_checked') == 1:
                    old_scores_json = json.loads(curr['scores']) if curr.get('scores') else {}
                    final_scores = old_scores_json.copy()
                    for k, v in new_auto_scores.items():
                        if old_scores_json.get(k, 0) == 0:
                            final_scores[k] = v
                
                item_to_save = {
                    'id': cid,
                    'grade': curr_grade,
                    'raw': clean_raw,
                    'scores': final_scores,
                    'is_checked': curr.get('is_checked', 0),
                    'weight': curr.get('weight', 0),
                    'target_thick': curr.get('target_thick', 0),
                    'target_width': curr.get('target_width', 0),
                    'production_date': curr.get('production_date'),
                    'slab_grade': curr.get('slab_grade'),
                    'factory': factory_id,
                    'Temperature': curr.get('Temperature', 0),
                    'Speed': curr.get('Speed', 0)
                }
                batch_save.append(item_to_save)

            if batch_save:
                db.save_batch_coils_v2(batch_save)
                print(f"✅ [Early TPHH] Đã cập nhật TPHH sớm cho {len(batch_save)} cuộn.")

    except Exception as e:
        print(f"❌ [Early TPHH Error] {e}")
def process_and_save_geometry(data_rows,factory_id="HRC1"):
    """
    Hàm core: Nhận list data từ API Geometry -> Map dữ liệu -> Lưu DB
    [UPDATE]: Ghi đè Raw Data + Bảo vệ điểm số nếu đã chốt tay (is_checked=1)
    """
    processed_ids = []
    batch_data = []
    coil_slab_map = {}
    conn = db.get_connection()

    cursor = conn.cursor()
    cursor.execute("SELECT coil_id, raw_data, grade, scores, is_checked FROM coil_data WITH (NOLOCK)")
    existing_rows = db.fetchall_as_dict(cursor) # <--- DÙNG HÀM MỚI
    conn.close()

    existing_map = {r['coil_id']: {
        'raw': json.loads(r['raw_data']) if r['raw_data'] else {}, 
        'grade': r['grade'],
        'scores': json.loads(r['scores']) if r['scores'] else {},
        'is_checked': r['is_checked']
    } for r in existing_rows}

    for row in data_rows:
        if 'debug_printed' not in globals():
            globals()['debug_printed'] = True
        r_id = row.get('TASK_SLAB') or row.get('piece_id') or row.get('COIL_ID') or row.get('SLAB_ID')
        if not r_id: continue
        coil_id = str(r_id).strip().upper()

        raw_map = {}
        if row.get('AVG_CROWN') is not None: raw_map['Crown'] = float(row.get('AVG_CROWN'))
        if row.get('AVG_WEDGE') is not None: raw_map['Wedge'] = float(row.get('AVG_WEDGE'))
        if row.get('FLATNEES') is not None: raw_map['Flatness'] = float(row.get('FLATNEES')) 

        val_prod_date = row.get('ARCHIVE_DATE') or row.get('PROD_DATE')
        clean_date = clean_date_sql(val_prod_date)
        if clean_date:
            raw_map['production_date'] = clean_date
        
        val_slab_grade = row.get('SLAB_ID') or row.get('BILLET_GRADE')
        cleaned_slab_id = None 
        
        if val_slab_grade:
            raw_slab = str(val_slab_grade).strip()
            
            # 🏭 LOGIC CHO NHÀ MÁY HRC 1 (Cắt đầu đuôi)
            # Ví dụ: [72451] -> 72451
            if factory_id == 'HRC1':
                if len(raw_slab) >= 2:
                    cleaned_slab_id = raw_slab[1:-1]
                else:
                    cleaned_slab_id = raw_slab

            # 🏭 LOGIC CHO NHÀ MÁY HRC 2 (Cắt bỏ 3 ký tự cuối)
            # Ví dụ: 72451001 -> 72451
            elif factory_id == 'HRC2':
                if len(raw_slab) > 3:
                    cleaned_slab_id = raw_slab[:-3]
                else:
                    cleaned_slab_id = raw_slab
            
            # Mặc định (giữ nguyên nếu không khớp logic trên)
            else:
                cleaned_slab_id = raw_slab

            # Thêm vào map để lát nữa query TPHH
            if cleaned_slab_id:
                coil_slab_map[coil_id] = cleaned_slab_id
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
        
        has_weight = pd.notnull(weight_val) and weight_val > 0
        
        if not clean_raw and not has_weight: 
            continue
        current_info = existing_map.get(coil_id, {'raw': {}, 'grade': 'SAE1006', 'scores': {}, 'is_checked': 0})
        
        final_grade = current_info['grade']
        api_grade = str(row.get('STEEL_GRADE', '')).strip().upper()
        if final_grade == 'SAE1006' and api_grade and api_grade not in ['NONE', '', 'NULL']:
            final_grade = api_grade

        full_raw = current_info['raw'].copy()
        full_raw.update(clean_raw) # Ghi đè dữ liệu mới vào
        new_auto_scores = process_coil_scores(coil_id, full_raw, final_grade)
        
        final_scores = new_auto_scores # Mặc định lấy điểm máy
        
        # Nếu đã sửa tay (is_checked == 1) -> Giữ nguyên điểm cũ
        if current_info.get('is_checked') == 1: 
            old_scores = current_info['scores']
            final_scores = old_scores.copy() # Bắt đầu bằng điểm cũ
            
            for k, v in new_auto_scores.items():
                if old_scores.get(k, 0) == 0:
                    final_scores[k] = v
        NhietDoSauCan = row.get('ACTUAL_EOR_TEMP') or 0
        NhietDoTaoCuon = row.get('DC_TEMP_AVERAGE') or 0
        item_to_save={
            'id': coil_id, 
            'grade': final_grade, 
            'raw': full_raw, 
            'scores': final_scores,
            'is_checked': current_info.get('is_checked', 0),
            'weight': float(weight_val) if pd.notnull(weight_val) else 0,
            'target_thick': float(tgt_thick) if pd.notnull(tgt_thick) else 0,
            'target_width': float(tgt_width) if pd.notnull(tgt_width) else 0,
            'production_date': clean_date,
            'factory': factory_id,
            'slab_grade': cleaned_slab_id if cleaned_slab_id else None,
            'Temperature': float(NhietDoSauCan),
            'Speed': float(NhietDoTaoCuon)
        }
        debug_check_data("GEOMETRY", item_to_save) 

        batch_data.append(item_to_save)
        processed_ids.append(coil_id)

    if batch_data:
        count_updated = 0
        db.save_batch_coils_v2(batch_data)
        count_updated = len(batch_data)
        print(f"✅ [Surface] Đã đồng bộ {count_updated} cuộn.")
        if coil_slab_map:
            threading.Thread(target=sync_tphh_from_slabs, args=(coil_slab_map, factory_id)).start()
    return processed_ids

def sync_surface_defects(target_ids=None,factory_id="HRC1"):

    with upload_lock:
        if not target_ids: return 0
        cfg = FACTORY_CONFIGS.get(factory_id)
        if not cfg: return 0
        current_api_surf = cfg['api_surf']
        conn = db.get_connection()
        placeholders = ','.join('?' * len(target_ids))
        query = f"SELECT coil_id, raw_data, grade, scores, is_checked, Temperature, Speed FROM coil_data WITH (NOLOCK) WHERE coil_id IN ({placeholders})"
        cursor = conn.cursor()
        cursor.execute(query, target_ids)
        existing_rows = db.fetchall_as_dict(cursor) 
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
                url = f"{current_api_surf}{coil_id}"
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
                    old_scores = curr['scores']
                    final_scores = old_scores.copy() # Bắt đầu bằng điểm cũ
                    
                    # Duyệt qua các điểm mới tính toán
                    for k, v in new_auto_scores.items():
                        # Nếu điểm cũ chưa có (0) hoặc không tồn tại -> Cho phép ghi đè bằng điểm mới (v)
                        # Giữ nguyên điểm cũ nếu nó đã có giá trị (> 0) để tôn trọng thao tác tay của user
                        if old_scores.get(k, 0) == 0:
                            final_scores[k] = v
                
                item_to_save ={
                    'id': coil_id, 'grade': curr['grade'], 'raw': clean_raw, 
                    'scores': final_scores, 
                    'is_checked': curr.get('is_checked', 0),
                    'factory': factory_id,
                    'Temperature': existing_map.get(coil_id, {}).get('Temperature', 0),
                    'Speed': existing_map.get(coil_id, {}).get('Speed', 0)
                }
                debug_check_data("SURFACE", item_to_save)

                batch_save.append(item_to_save)
            except: continue

        count_updated = 0
        if batch_save:
            db.save_batch_coils_v2(batch_save)
            count_updated = len(batch_save)
            print(f"✅ [Surface] Đã đồng bộ {count_updated} cuộn.")
            
        return count_updated


def sync_properties_mysql(target_ids=None,factory_id="HRC1"):
    if not target_ids: return 0
    cfg = FACTORY_CONFIGS.get(factory_id)
    if not cfg: return 0
    
    current_db_conn = cfg['db_conn']      # Thông tin user/pass/host
    current_view_cotinh = cfg['db_prop_view'] # Tên view cơ tính
    current_view_tphh = cfg['db_tphh_view']
    CHUNK_SIZE = 100
    updated_ids_list = []
    
    for i in range(0, len(target_ids), CHUNK_SIZE):
        chunk_ids = target_ids[i : i + CHUNK_SIZE]
        print(f"🧪 [Properties] Đang xử lý gói {i//CHUNK_SIZE + 1}: {len(chunk_ids)} cuộn...")
        
        # 1. Lấy dữ liệu từ MySQL (Giữ nguyên logic cũ)
        ids_str = ",".join([f"'{str(x)}'" for x in chunk_ids])
        final_data_map = {} 
        slab_to_coils_map = {}

        try:
            conn_mysql = pymysql.connect(**current_db_conn, cursorclass=pymysql.cursors.DictCursor)
            with conn_mysql.cursor() as cursor:
                # ... (Đoạn query MySQL GIỮ NGUYÊN không đổi) ...
                sql_cotinh = f"SELECT * FROM {current_view_cotinh} WHERE SUBSTRING_INDEX({COL_ID_CUON}, '/', 1) IN ({ids_str})"
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

                if target_slabs:
                    slabs_str = ",".join([f"'{str(x)}'" for x in target_slabs])
                    sql_tphh = f"SELECT * FROM {current_view_tphh} WHERE {COL_ID_PHOI_TPHH} IN ({slabs_str})"
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
            
            # 2. LƯU VÀO DB LOCAL (CÓ SỬA ĐỔI ĐỂ BẢO TOÀN DỮ LIỆU CŨ)
            if final_data_map: 
                batch_save = []
                conn_local = db.get_connection()
                clean_ids_found = list(final_data_map.keys())
                placeholders = ','.join('?' * len(clean_ids_found))
                
                # [QUAN TRỌNG] Lấy đầy đủ các cột cũ để không bị ghi đè NULL
                query = f"""
                    SELECT coil_id, raw_data, grade, scores, is_checked, 
                           weight, target_thick, target_width, production_date, slab_grade,
                           Temperature, Speed -- <--- THÊM
                    FROM coil_data WITH (NOLOCK) WHERE coil_id IN ({placeholders})
                """
                
                cursor = conn_local.cursor()
                cursor.execute(query, clean_ids_found)
                # Dùng hàm helper mới để lấy Dict
                existing_rows = db.fetchall_as_dict(cursor)
                conn_local.close()

                # Map theo ID để tra cứu nhanh
                existing_map = {r['coil_id']: r for r in existing_rows}

                for cid, new_props in final_data_map.items():
                    # Lấy dữ liệu cũ, nếu không có thì tạo mặc định
                    curr = existing_map.get(cid, {})
                    
                    # Parse Raw Data cũ
                    old_raw = json.loads(curr['raw_data']) if curr.get('raw_data') else {}
                    
                    # Merge Cơ tính mới vào Raw cũ
                    final_raw = old_raw.copy()
                    final_raw.update(new_props)
                    clean_raw = sanitize_data(final_raw)
                    
                    # Tính điểm lại
                    curr_grade = curr.get('grade', 'SAE1006')
                    new_auto_scores = process_coil_scores(cid, clean_raw, curr_grade)
                    
                    # Logic bảo vệ điểm tay (như cũ)
                    final_scores = new_auto_scores
                    if curr.get('is_checked') == 1:
                        old_scores_json = json.loads(curr['scores']) if curr.get('scores') else {}
                        final_scores = old_scores_json.copy()
                        for k, v in new_auto_scores.items():
                            if old_scores_json.get(k, 0) == 0:
                                final_scores[k] = v
                    
                    item_to_save={
                        'id': cid, 
                        'grade': curr_grade, 
                        'raw': clean_raw, 
                        'scores': final_scores, 
                        'is_checked': curr.get('is_checked', 0),
                        
                        # --- [FIX QUAN TRỌNG]: TRUYỀN LẠI DỮ LIỆU CŨ ---
                        'weight': curr.get('weight', 0),
                        'target_thick': curr.get('target_thick', 0),
                        'target_width': curr.get('target_width', 0),
                        'production_date': curr.get('production_date'),
                        'slab_grade': curr.get('slab_grade'),
                        'factory': factory_id,
                        'Temperature': curr.get('Temperature', 0),
                        'Speed': curr.get('Speed', 0)           
                    }
                    debug_check_data("PROPERTIES", item_to_save)

                    batch_save.append(item_to_save)
                if batch_save: 
                    db.save_batch_coils_v2(batch_save)
                    updated_ids_list.extend([item['id'] for item in batch_save])
                    
        except Exception as e:
            continue 

    return updated_ids_list
# Quét lại các cuộn gần nhất để bù đắp cơ tính
def rescan_recent_coils_for_mechanical():
    print("\n--- 🐢 BẮT ĐẦU QUÉT BÙ CƠ TÍNH (SMART SCAN) ---")
    for factory_id in FACTORY_CONFIGS:
        try:
            conn = db.get_connection()
            query = "SELECT TOP 5000 coil_id, raw_data FROM coil_data WITH (NOLOCK) WHERE factory = ? ORDER BY production_date DESC"
            
            cursor = conn.cursor()
            cursor.execute(query, (factory_id,))
            rows = db.fetchall_as_dict(cursor) # <--- DÙNG HÀM MỚI
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
                    if not raw.get('YieldPoint') or not raw.get('Hardness'):
                        target_ids.append(r['coil_id'])
                except:
                    # Nếu lỗi parse JSON -> Coi như dữ liệu lỗi/trống -> Cho vào danh sách quét lại
                    target_ids.append(r['coil_id'])

            if not target_ids:
                print(f"✅ Đã kiểm tra {len(rows)} cuộn gần nhất. Tất cả đều ĐÃ CÓ đủ cơ tính. Không cần quét.")
                return

            updated_ids = sync_properties_mysql(target_ids, factory_id)
            
            if updated_ids:
                count = len(updated_ids)
                # Tạo thông báo chi tiết
                if count <= 5:
                    # Nếu ít (<= 5 cuộn) thì liệt kê hết: "HRC1, HRC2"
                    id_str = ", ".join(updated_ids)
                    msg = f"Đã bù cơ tính ({count}): {id_str}"
                else:
                    # Nếu nhiều thì chỉ hiện 3 cuộn đầu + số lượng còn lại
                    first_few = ", ".join(updated_ids[:3])
                    msg = f"Đã bù cơ tính ({count}): {first_few} và {count-3} cuộn khác."
                
                notify_frontend(msg, title="Cập nhật Cơ tính")

        except Exception as e:
            print(f"❌ Lỗi Job Bù đắp: {str(e)}")
        
        print("--- 🏁 KẾT THÚC QUÉT BÙ ---\n")

scheduler = BackgroundScheduler()
# Scheduler initialization
def init_scheduler():
    if not scheduler.running:
        scheduler.add_job(rescan_recent_coils_for_mechanical, trigger="interval", minutes=60, id='mechanical_catchup_job', replace_existing=True, next_run_time=datetime.now() + pd.Timedelta(minutes=1))
        scheduler.start()
        print("🚀 Khởi động WebSocket Listener...")
        start_websocket_listener()

# Chạy thông tinh đồng bộ ngay lập tức cho 1 cuộn
def run_immediate_sync(target_id, factory_id="HRC1"):
    global processing_coils
    cfg = FACTORY_CONFIGS.get(factory_id)
    if not cfg: 
        print(f"❌ Config không tồn tại cho {factory_id}")
        return
    MAX_RETRIES = 5
    RETRY_DELAY = 2 

    try:
        details = []   
        # --- 1. Surface (Cũng nên Retry nếu cần, nhưng thường Surface API chậm hơn Geo) ---
        cnt = 0
        for attempt in range(MAX_RETRIES):
            cnt = sync_surface_defects([target_id], factory_id)
            if cnt > 0: 
                break
            else:
                if attempt < 2: time.sleep(1) 
        
        if cnt > 0: details.append("Bề mặt (OK)")
        else: details.append("Bề mặt (0)")

        # --- 2. Geometry (Quan trọng: API này hay bị trễ 2-5s) ---
        geo_ok = False
        api_url = f"{cfg['api_geo']}{target_id}"
        
        for attempt in range(MAX_RETRIES):
            try:
                res = requests.get(api_url, timeout=5)
                
                # Check kỹ xem có dữ liệu thực sự không
                has_data = False
                if res.status_code == 200:
                    rows = res.json()
                    if isinstance(rows, dict): rows = rows.get('data', [])
                    if rows and len(rows) > 0:
                        has_data = True
                        # Có dữ liệu -> Xử lý và THOÁT VÒNG LẶP NGAY
                        process_and_save_geometry(rows, factory_id)
                        geo_ok = True
                        print(f"✅ [Geo] Lấy thành công ở lần thử {attempt + 1}")
                        break 
                
                # Nếu chưa có dữ liệu hoặc lỗi
                print(f"⏳ [Geo] Lần {attempt + 1}: API chưa trả về dữ liệu. Đợi {RETRY_DELAY}s...")
                time.sleep(RETRY_DELAY) # Ngủ 2s
                
            except Exception as e:
                print(f"⚠️ [Geo] Lỗi kết nối lần {attempt + 1}: {e}")
                time.sleep(RETRY_DELAY)

        if geo_ok: details.append("Hình học (OK)")
        else: details.append("Hình học (Lỗi/Trễ)")
        
        # 3. Thông báo chi tiết
        final_msg = f"[{factory_id}] Cuộn {target_id} - " + ", ".join(details)
        notify_frontend(final_msg, title="Auto Sync")

    except Exception as e:
        print(f"❌ Sync Error {target_id}: {e}")
        notify_frontend(f"Lỗi quét {target_id}: {str(e)}", title="Lỗi Hệ Thống")
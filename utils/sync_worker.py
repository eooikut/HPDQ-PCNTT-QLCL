from flask import Blueprint, app, render_template, current_app, request, jsonify
import pandas as pd
import threading
import json
import db  
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
from utils.Bkmis import temp_api_worker, push_to_temp_queue
ML_API_URL = "http://localhost:8000/predict"  # Đổi IP nếu API cài ở máy khác

def call_ml_prediction(coil_id, raw_data, curr_item):
    """Hàm gom dữ liệu và gọi API AI dự đoán tức thời"""
    try:
        # Chuẩn bị gói dữ liệu gửi cho AI (Mapping đúng tên biến)
        payload = {
            "Coil_ID": str(coil_id),
            "Target_Thick": float(curr_item.get('target_thick') or 0),
            "Target_Width": float(curr_item.get('target_width') or 0),
            "FDT": float(curr_item.get('Temperature') or raw_data.get('ACTUAL_EOR_TEMP') or 0), # Nhiệt độ kết thúc cán
            "CT": float(curr_item.get('Speed') or raw_data.get('DC_TEMP_AVERAGE') or 0),        # Nhiệt độ cuộn
            "C": float(raw_data.get('C', 0)),
            "Mn": float(raw_data.get('Mn', 0)),
            "Si": float(raw_data.get('Si', 0)),
            "P": float(raw_data.get('P', 0)),
            "S": float(raw_data.get('S', 0)),
            "Crown": float(raw_data.get('Crown', 0)),
            "Wedge": float(raw_data.get('Wedge', 0)),
            "Al": float(raw_data.get('Al', 0))
        }

        # Bắn request lên API
        response = requests.post(ML_API_URL, json=payload, timeout=5)
        if response.status_code == 200:
            result = response.json()
            preds = result.get('Predictions', {})
            print(f"🤖 [AI Dự đoán] {coil_id} - Yield: {preds.get('YieldPoint_MPa')} MPa")
            
            # Trả về kết quả dự đoán và Cảnh báo QC để lưu vào DB hiển thị Web
            return {
                "Pred_Yield": preds.get('YieldPoint_MPa'),
                "Pred_Tensile": preds.get('Tensile_MPa'),
                "Pred_Elongation": preds.get('Elongation_Pct'),
                "AI_Warnings": result.get('QC_Warnings', [])
            }
        else:
            print(f"⚠️ [ML API Lỗi] {coil_id}: {response.text}")
            return None
    except Exception as e:
        print(f"❌ [Lỗi Gọi ML API] {coil_id}: {e}")
        return None

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
        val_str = str(value) if value is not None else ""
        val_len = len(val_str)
        if val_len > 45 and key not in ['raw', 'scores', 'raw_data']:
            has_error = True
    
    if not has_error:
        print("   ✅ Dữ liệu an toàn.")
    else:
        print("   ❌ PHÁT HIỆN NGUY CƠ LỖI!")
# =======================================================
COIL_COOLDOWN_CACHE = {}
API_GEO_SINGLE_URL = "http://10.192.49.39:5026/hsm?piece_id=" 
API_SURFACE_URL = "http://10.192.49.39:5025/defects?customer_id=" 
FACTORY_CONFIGS = {
    'HRC1': {
        'name': 'Nhà máy HRC 1',
        'api_geo': 'http://10.192.49.39:5026/hsm?piece_id=', 
        'api_surf': 'http://10.192.49.39:5025/defects?customer_id=',
        'ws_url': 'ws://10.192.49.39:8001/ws',
        'db_prop_view': 'view_hrcproduct',
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
        'db_prop_view': 'view_hrcproduct',
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
COL_ID_CUON = "ProductName"      
COL_ID_PHOI_COTINH = "BilletLotname"   
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

def notify_frontend(msg, title="Cập nhật dữ liệu", factory_id='ALL'):
    """Hàm cập nhật trạng thái: Vừa báo Web, Vừa lưu DB"""
    global LAST_DATA_UPDATE, LAST_NOTIFY_CACHE

    with notify_lock:
        current_time = time.time()
        full_msg = f"[{factory_id}] {title}: {msg}" 
        
        if full_msg == LAST_NOTIFY_CACHE['message']:
            if (current_time - LAST_NOTIFY_CACHE['time']) < 60:
                return 

        LAST_NOTIFY_CACHE['message'] = full_msg
        LAST_NOTIFY_CACHE['time'] = current_time

        LAST_DATA_UPDATE['timestamp'] = current_time
        LAST_DATA_UPDATE['message'] = full_msg
        
    from routes.dashboard import log_system_event
    try:
        log_system_event(title, msg, 'success', factory=factory_id)
    except:
        pass
# =======================================================
# PHẦN 2: WEBSOCKET CLIENT (REALTIME)
# =======================================================
def is_coil_in_db(coil_id):
    conn = None
    try:
        conn = db.get_connection()
        cursor = conn.cursor()
        row = cursor.execute("SELECT 1 FROM coil_data WITH (NOLOCK) WHERE coil_id = ?", (coil_id,)).fetchone()
        return row is not None
    except Exception as e:
        print(f"Lỗi check DB ({coil_id}): {e}")
        return False
    finally:
        if conn:
            conn.close() # Đảm bảo luôn đóng
def on_ws_message(ws, message, factory_id):
    global COIL_COOLDOWN_CACHE
    try:
        response = json.loads(message)
        if not isinstance(response, dict): return
        
        data = response.get('data', {})
        
        # 1. NHÁNH REALTIME: Lấy MarkingText để tạo mới và phân cấp
        marking_id = data.get('MarkingText')
        if marking_id:
            marking_id = str(marking_id).strip().upper()
            current_ts = time.time()
            
            # Kiểm tra Cooldown để không spam API cho cùng 1 cuộn
            if marking_id not in COIL_COOLDOWN_CACHE:
                if not is_coil_in_db(marking_id):
                    COIL_COOLDOWN_CACHE[marking_id] = current_ts
                    # Chạy đồng bộ Geometry + Surface ngay lập tức
                    threading.Thread(target=run_immediate_sync, args=(marking_id, factory_id)).start()

        # 2. NHÁNH UPDATE: Lấy Cam43Marktxt để cập nhật khối lượng
        cam43_id = data.get('Cam43Marktxt')
        cam43_weight = data.get('Cam43Weight')
        
        if cam43_id and cam43_weight:
            cam43_id = str(cam43_id).strip().upper()
            threading.Thread(target=update_coil_weight_only, args=(cam43_id, cam43_weight)).start()
            
    except Exception as e:
        print(f"⚠️ WS Parse Error ({factory_id}): {e}")
def update_coil_weight_only(coil_id, weight):
    try:
        if weight is None: return
        if isinstance(weight, str): weight = weight.replace(',', '')
        weight_val = float(weight)
        if weight_val <= 0: return
    except ValueError:
        return
        
    conn = None
    try:
        conn = db.get_connection()
        cursor = conn.cursor()
        sql = """
            UPDATE coil_data 
            SET weight = ? 
            WHERE coil_id = ? 
              AND (weight IS NULL OR weight = 0)
        """
        cursor.execute(sql, (weight_val, coil_id))
        conn.commit()
    except Exception as e:
        print(f"❌ [Weight Error] {coil_id}: {e}")
    finally:
        if conn: 
            conn.close()

def on_ws_error(ws, error): print(f"❌ [WS Error] {error}")
# def on_ws_close(ws, status, msg):
#     print("🔌 [WS] Closed. Reconnecting in 5s...")
#     time.sleep(5)
#     start_websocket_listener()

def start_websocket_listener():
    """Khởi động lắng nghe cho TẤT CẢ nhà máy trong Config với cơ chế Auto-Reconnect bền bỉ"""
    
    # Header giả lập trình duyệt để tránh bị chặn
    headers = {
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
    }
    
    for fid, cfg in FACTORY_CONFIGS.items():
        
        def run_single_listener(f_id):
            target_url = FACTORY_CONFIGS[f_id]['ws_url']
            
            # Vòng lặp vô hạn giữ Thread sống trọn đời
            while True:
                try:
                    print(f"🔄 [WS - {f_id}] Đang cố gắng kết nối tới {target_url}...")
                    
                    def on_message(ws, msg):
                        on_ws_message(ws, msg, f_id) 
                        
                    def on_error(ws, error):
                        print(f"❌ [WS - {f_id}] Lỗi: {error}")

                    def on_close(ws, close_status_code, close_msg):
                        print(f"🔌 [WS - {f_id}] Mất kết nối (Mã: {close_status_code}). Đang chuẩn bị thử lại...")

                    def on_open(ws):
                        print(f"✅ [WS - {f_id}] Kết nối thành công! Đang lắng nghe dữ liệu...")

                    # Khởi tạo mới instance mỗi lần reconnect để dọn dẹp session cũ
                    ws = websocket.WebSocketApp(
                        target_url,
                        on_open=on_open,
                        on_message=on_message,
                        on_error=on_error,
                        on_close=on_close,
                        header=headers
                    )
                    
                    # Hàm chặn luồng. Giữ ping_interval để phát hiện kết nối chết lâm sàng (half-open)
                    ws.run_forever()
                    
                except Exception as e:
                    print(f"⚠️ [WS - {f_id}] Bị văng ngoại lệ Thread: {e}")
                
                # Chờ 5 giây trước khi kết nối lại để không bị quá tải máy chủ (DDoS chính mình) nếu server down
                print(f"⏳ [WS - {f_id}] Đợi 2s trước khi reconnect...")
                time.sleep(2)

        # Khởi tạo đúng 1 Thread cho 1 nhà máy lúc khởi động app
        t = threading.Thread(target=run_single_listener, args=(fid,), daemon=True)
        t.start()
# =======================================================
# Hàm đồng bộ TPHH dựa trên Mác phôi (Lấy từ Geometry)
def sync_tphh_from_slabs(coil_slab_map, factory_id="HRC1"):
    """
    coil_slab_map: Dict { 'COIL_ID': 'SLAB_ID', ... }
    Mục tiêu: Lấy TPHH ngay khi có Geometry mà không cần chờ Cơ tính.
    """
    if not coil_slab_map: return
    
    cfg = FACTORY_CONFIGS.get(factory_id)
    if not cfg: return
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
            sql_tphh = f"SELECT * FROM {current_view_tphh} WHERE {COL_ID_PHOI_TPHH} IN ({slabs_str}) AND BilletSampleName = 'TSC9'"
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
                        tphh_elements = [
                            'C', 'Si', 'Mn', 'S', 'P', 'Cu', 'Ni', 'Cr', 'Mo', 
                            'V', 'Ti', 'Al', 'Ca', 'B', 'Nb', 'CEV', 'O', 'N', 'H'
                        ]
                        for el in tphh_elements:
                            if r.get(el) is not None:
                                final_data_map[coil_id][el] = float(r[el])
        conn_mysql.close()

        # 2. Lưu vào Database Local (Merge với dữ liệu cũ)
        if final_data_map:
            batch_save = []
            conn_local = None
            existing_rows = []
            try:
                conn_local = db.get_connection()
                
                # Lấy dữ liệu hiện tại để merge
                placeholders = ','.join('?' * len(final_data_map))
                keys = list(final_data_map.keys())
                
                query = f"""
                    SELECT c.coil_id, c.raw_data, c.grade, c.scores, c.is_checked, 
                        c.weight, c.target_thick, c.target_width, c.production_date, c.slab_grade,
                        c.Temperature, c.Speed, c.TARGET_LV2
                    FROM coil_data c WITH (NOLOCK) 
                    WHERE c.coil_id IN ({placeholders})
                    AND NOT EXISTS (
                        SELECT 1 
                        FROM sanluong sl WITH (NOLOCK) 
                        WHERE sl.[ID Cuộn bó] = c.coil_id 
                            AND sl.[Đã nhập kho] = N'Yes'
                    )
                """
                cursor = conn_local.cursor()
                cursor.execute(query, keys)
                existing_rows = db.fetchall_as_dict(cursor)
            except Exception as e:
                print(f"Lỗi đọc DB local TPHH: {e}")
            finally:
                if conn_local: 
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
                thickness_val = float(curr.get('TARGET_LV2') or 0.0)
                new_auto_scores = process_coil_scores(cid, clean_raw, curr_grade,thickness_val)

                # Bảo vệ điểm tay
                final_scores = new_auto_scores
                if curr.get('is_checked') == 1:
                    old_scores_json = json.loads(curr['scores']) if curr.get('scores') else {}
                    final_scores = old_scores_json.copy()
                    for k, v in new_auto_scores.items():
                        if old_scores_json.get(k, 0) == 0:
                            final_scores[k] = v
                if 'SAE1006' in curr_grade.upper():
                    ai_results = call_ml_prediction(cid, clean_raw, curr)
                    if ai_results:
                        # Lưu điểm AI vào JSON scores để Frontend hiển thị
                        # Lưu luôn cảnh báo vào raw_data nếu muốn Web hiện chuỗi cảnh báo
                        clean_raw['Pred_Yield'] = ai_results['Pred_Yield']
                        clean_raw['Pred_Tensile'] = ai_results['Pred_Tensile']
                        clean_raw['Pred_Elongation'] = ai_results['Pred_Elongation']
                        clean_raw['AI_Warnings'] = ai_results['AI_Warnings']
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
                    'Speed': curr.get('Speed', 0),
                    'TARGET_LV2': curr.get('TARGET_LV2', 0)
                }
                batch_save.append(item_to_save)

            if batch_save:
                db.save_batch_coils_v2(batch_save)

    except Exception as e:
        print(f"❌ [Early TPHH Error] {e}")
import math
def safe_float(val):
        """Hàm bảo vệ ép kiểu an toàn, diệt trừ tận gốc NaN"""
        try:
            # Ép kiểu thông thường
            res = float(val)
            # Nếu kết quả là NaN (Not a Number) thì ép về 0.0
            if math.isnan(res):
                return 0.0
            return res
        except (ValueError, TypeError):
            return 0.0
def process_and_save_geometry(data_rows,factory_id="HRC1"):
    target_ids = []
    for row in data_rows:
        r_id = row.get('TASK_SLAB') or row.get('piece_id') or row.get('COIL_ID') or row.get('SLAB_ID')
        if r_id: target_ids.append(str(r_id).strip().upper())
        
    if not target_ids: return []
    processed_ids = []
    batch_data = []
    partner_api_batch = []
    coil_slab_map = {}
    conn = None
    existing_rows = []
    try:
        conn = db.get_connection()
        cursor = conn.cursor()
        placeholders = ','.join('?' * len(target_ids))
        query = f"SELECT coil_id, raw_data, grade, scores, is_checked, quality_level, note_qc FROM coil_data WITH (NOLOCK) WHERE coil_id IN ({placeholders})"
        cursor.execute(query, target_ids)
        
        existing_rows = db.fetchall_as_dict(cursor)
    except Exception as e:
        print(f"Lỗi đọc DB trong Geometry: {e}")
        return [] # Thoát hàm sớm nếu lỗi để không chết luồng
    finally:
        if conn:
            conn.close()

    existing_map = {r['coil_id']: {
        'raw': json.loads(r['raw_data']) if r['raw_data'] else {}, 
        'grade': r['grade'],
        'scores': json.loads(r['scores']) if r['scores'] else {},
        'is_checked': r['is_checked'],
        'quality_level': r.get('quality_level'),
        'note_qc': r.get('note_qc')
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
        if row.get('THICK_MIN') is not None: 
            raw_map['ThickMin'] = float(pd.to_numeric(row.get('THICK_MIN'), errors='coerce') or 0)
        if row.get('THICK_MAX') is not None: 
            raw_map['ThickMax'] = float(pd.to_numeric(row.get('THICK_MAX'), errors='coerce') or 0)
        if row.get('WIDTH_MIN') is not None: 
            raw_map['WidthMin'] = float(pd.to_numeric(row.get('WIDTH_MIN'), errors='coerce') or 0)
        if row.get('WIDTH_MAX') is not None: 
            raw_map['WidthMax'] = float(pd.to_numeric(row.get('WIDTH_MAX'), errors='coerce') or 0)
        
        if row.get('DC_TEMP_MAX') is not None:
            raw_map['DcTempMax'] = safe_float(row.get('DC_TEMP_MAX'))
        if row.get('DC_TEMP_MIN') is not None:
            raw_map['DcTempMin'] = safe_float(row.get('DC_TEMP_MIN'))
        if row.get('THICK') is not None:
            raw_map['Thick'] = safe_float(row.get('THICK'))
        if row.get('WIDTH') is not None:
            raw_map['Width'] = safe_float(row.get('WIDTH'))
        if row.get('LENGTH') is not None:
            raw_map['Length'] = safe_float(row.get('LENGTH'))
        val_prod_date = row.get('ARCHIVE_DATE') or row.get('PROD_DATE')
        clean_date = clean_date_sql(val_prod_date)
        if clean_date:
            raw_map['production_date'] = clean_date
        
        val_slab_grade = row.get('SLAB_ID') or row.get('BILLET_GRADE')
        cleaned_slab_id = None 
        
        if val_slab_grade:
            raw_slab = str(val_slab_grade).strip()
            
            # 🏭 LOGIC CHO NHÀ MÁY HRC 1 (Cắt đầu đuôi)
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
            
            else:
                cleaned_slab_id = raw_slab
            if cleaned_slab_id:
                coil_slab_map[coil_id] = cleaned_slab_id
        tgt_thick = pd.to_numeric(row.get('TARGTHK') or row.get('TARGET_THICK'), errors='coerce')
        act_thick = pd.to_numeric(row.get('THICK'), errors='coerce') 
        avg_thick = pd.to_numeric(row.get('AVG_THICK'), errors='coerce')
        if pd.notnull(act_thick) and pd.notnull(avg_thick):
            raw_map['ThickDiff'] = abs(act_thick - avg_thick)

        # 2. Rộng mục tiêu
        tgt_width = pd.to_numeric(row.get('TARGWIDTH') or row.get('TARGET_WIDTH'), errors='coerce')
        act_width = pd.to_numeric(row.get('WIDTH'), errors='coerce')
        
        # Lấy giá trị, mặc định là 0 nếu không tồn tại trong dict
        w_min = raw_map.get('WidthMin', 0)
        w_max = raw_map.get('WidthMax', 0)

        if pd.notnull(tgt_width):
            # KIỂM TRA CHẶT: Phải > 0 mới tính là có dữ liệu thực tế đo được
            if (w_min > 0 and w_min < tgt_width) or \
               (w_max > 0 and w_max > tgt_width + 25):
                raw_map['WidthDiff'] = 26.0  # Gán 26 để ép vào C6 (>25)
            
            # Logic cũ giữ nguyên
            elif pd.notnull(act_width):
                raw_map['WidthDiff'] = abs(act_width - tgt_width)
        api_slab_grade_name = row.get('SLAB_GRADE') or row.get('BILLET_GRADE_NAME') or None
        # 3. Khối lượng (Cần check kỹ key của API trả về, thường là WEIGHT, COIL_WEIGHT, hoặc MASS)
        raw_weight = row.get('KhoiLuongPDI') or row.get('COIL_WEIGHT')
        if isinstance(raw_weight, str):
            raw_weight = raw_weight.replace(',', '') 

        weight_val = pd.to_numeric(raw_weight, errors='coerce')
        
        clean_raw = sanitize_data(raw_map)
        
        has_weight = pd.notnull(weight_val) and weight_val > 0
        
        if not clean_raw and not has_weight: 
            continue
        current_info = existing_map.get(coil_id, {'raw': {}, 'grade': 'SAE1006', 'scores': {}, 'is_checked': 0})
        
        final_grade = current_info['grade']
        thickness_val = float(avg_thick) if pd.notnull(avg_thick) else 0.0
        api_grade = str(row.get('STEEL_GRADE', '')).strip().upper()
        if final_grade == 'SAE1006' and api_grade and api_grade not in ['NONE', '', 'NULL']:
            final_grade = api_grade

        full_raw = current_info['raw'].copy()
        full_raw.update(clean_raw) # Ghi đè dữ liệu mới vào
        new_auto_scores = process_coil_scores(coil_id, full_raw, final_grade, thickness_val)
        
        final_scores = new_auto_scores # Mặc định lấy điểm máy
        
        # Nếu đã sửa tay (is_checked == 1) -> Giữ nguyên điểm cũ
        if current_info.get('is_checked') == 1: 
            old_scores = current_info['scores']
            final_scores = old_scores.copy() # Bắt đầu bằng điểm cũ
            
            for k, v in new_auto_scores.items():
                if old_scores.get(k, 0) == 0:
                    final_scores[k] = v
        NhietDoSauCan = safe_float(row.get('ACTUAL_EOR_TEMP'))
        actual_dc = safe_float(row.get('DC_TEMP_AVERAGE'))
        target_fm = safe_float(row.get('TARGET_FM_TEMP_EXIT'))
        target_dc = safe_float(row.get('TARGET_DC_TEMP_EXIT'))
        NhietDoTaoCuon = actual_dc if actual_dc > 0 else target_dc
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
            'Temperature': NhietDoSauCan,
            'Speed': NhietDoTaoCuon,
            'slab_grade_name': str(api_slab_grade_name).strip() if api_slab_grade_name else None,
            'target_temp_finish': target_fm,
            'target_temp_coil': target_dc,
            'quality_level': current_info.get('quality_level'),
            'note_qc': current_info.get('note_qc'),
            'TARGET_LV2': float(avg_thick) if pd.notnull(avg_thick) else 0,
        }
        debug_check_data("GEOMETRY", item_to_save) 
        

        # Rẽ nhánh lấy đúng trường thick_avg theo nhà máy
        source_thick_avg_key = 'AVG_THICK' if factory_id == 'HRC1' else 'THICK'

        api_payload = {
            "idCuonBo": str(coil_id),
            "temp": NhietDoTaoCuon,
            "temp_min": safe_float(row.get('DC_TEMP_MIN')),
            "temp_max": safe_float(row.get('DC_TEMP_MAX')),
            "thick_avg": safe_float(row.get(source_thick_avg_key)),
            "thick_min": safe_float(row.get('THICK_MIN')),
            "thick_max": safe_float(row.get('THICK_MAX')),
            "width_avg": safe_float(row.get('WIDTH')), # Viết đúng chính tả width_agv theo hình
            "width_min": safe_float(row.get('WIDTH_MIN')),
            "width_max": safe_float(row.get('WIDTH_MAX')),
            "length": safe_float(row.get('LENGTH'))
        }
        partner_api_batch.append(api_payload)
        batch_data.append(item_to_save)
        processed_ids.append(coil_id)

    if batch_data:
        count_updated = 0
        db.save_batch_coils_v2(batch_data)
        count_updated = len(batch_data)
        print(f"✅ [Geo] Đã đồng bộ {count_updated} cuộn.")
        for payload in partner_api_batch:
            push_to_temp_queue(payload)
        if coil_slab_map:
            threading.Thread(target=sync_tphh_from_slabs, args=(coil_slab_map, factory_id)).start()
    return processed_ids

def sync_surface_defects(target_ids=None, factory_id="HRC1"):
    if not target_ids: return 0
    cfg = FACTORY_CONFIGS.get(factory_id)
    if not cfg: return 0
    
    current_api_surf = cfg['api_surf']
    from utils.scoring import get_all_grade_configs
    all_configs = get_all_grade_configs()
    
    dynamic_whitelist = set()
    for grade_cfg in all_configs.values():
        for key, item_cfg in grade_cfg.items():
            if isinstance(item_cfg, dict) and item_cfg.get('group') == 'surface':
                dynamic_whitelist.add(key)
    
    # --- BƯỚC 1: LẤY DỮ LIỆU TỪ API (NGOÀI LOCK - ĐỂ KHÔNG TREO HỆ THỐNG) ---
    api_data_map = {} 
    for coil_id in target_ids:
        try:
            url = f"{current_api_surf}{coil_id}"
            resp = requests.get(url, timeout=5)
            if resp.status_code == 200:
                data = resp.json()
                raw_rows = data.get('rows', [])
                if raw_rows:
                    coil_defects = {}
                    for row in raw_rows:
                        defect = str(row.get('DefectClass')).strip()
                        if defect not in dynamic_whitelist: continue
                        try: val = float(row.get('Size'))
                        except: val = 0.0
                        if defect not in coil_defects: coil_defects[defect] = []
                        coil_defects[defect].append(val)
                    api_data_map[coil_id] = coil_defects
        except: continue

    if not api_data_map: return 0
    conn = None
    existing_rows = []
    try:
        conn = db.get_connection()
        # Chỉ lấy những ID thực sự có dữ liệu từ API để tối ưu query
        ids_to_query = list(api_data_map.keys())
        placeholders = ','.join('?' * len(ids_to_query))
        
        query = f"""
            SELECT coil_id, raw_data, grade, scores, is_checked, factory,
                    Temperature, Speed, 
                    weight, target_thick, target_width, production_date, slab_grade, quality_level, note_qc, target_temp_finish, target_temp_coil, TARGET_LV2
            FROM coil_data WITH (NOLOCK) WHERE coil_id IN ({placeholders})
        """
        cursor = conn.cursor()
        cursor.execute(query, ids_to_query)
        existing_rows = db.fetchall_as_dict(cursor) 
    except Exception as e:
        print(f"Lỗi đọc DB Surface: {e}")
    finally:
        if conn:
            conn.close()
    
    existing_map = {r['coil_id']: r for r in existing_rows}
    batch_save = []

    # Dùng dữ liệu API đã lấy ở Bước 1 để xử lý logic cũ của bạn
    for coil_id, coil_defects in api_data_map.items():
        try:
            curr = existing_map.get(coil_id, {})
            old_raw = json.loads(curr['raw_data']) if curr.get('raw_data') else {}
            final_raw = old_raw.copy()
            final_raw.update(coil_defects)
            clean_raw = sanitize_data(final_raw)
            curr_grade = curr.get('grade', 'SAE1006')
            thickness_val = float(curr.get('TARGET_LV2') or 0.0)
            new_auto_scores = process_coil_scores(coil_id, clean_raw, curr_grade, thickness_val)
            
            final_scores = new_auto_scores
            if curr.get('is_checked') == 1:
                old_scores = json.loads(curr['scores']) if isinstance(curr.get('scores'), str) else curr.get('scores', {})
                final_scores = old_scores.copy() 
                for k, v in new_auto_scores.items():
                    if old_scores.get(k, 0) == 0:
                        final_scores[k] = v
            
            item_to_save = {
                'id': coil_id, 'grade': curr_grade, 'raw': clean_raw, 'scores': final_scores,
                'is_checked': curr.get('is_checked', 0), 'factory': factory_id,
                'Temperature': curr.get('Temperature', 0), 'Speed': curr.get('Speed', 0),
                'weight': curr.get('weight', 0), 'target_thick': curr.get('target_thick', 0),
                'target_width': curr.get('target_width', 0), 'production_date': curr.get('production_date'),
                'slab_grade': curr.get('slab_grade'), 'quality_level': curr.get('quality_level'),
                'note_qc': curr.get('note_qc'),
                'target_temp_finish': curr.get('target_temp_finish', 0),
                'target_temp_coil': curr.get('target_temp_coil', 0),
                'TARGET_LV2': curr.get('TARGET_LV2', 0)
            }
            batch_save.append(item_to_save)
        except: continue

    if batch_save:
        db.save_batch_coils_v2(batch_save)
        return len(batch_save)
            
    return 0
MECH_KEYS = [
    # Cơ tính cốt lõi & mở rộng
    'YieldPoint', 'Tensile', 'Elongation', 'Hardness', 'ImpactEnergy', 
    # Thành phần hóa học cốt lõi
    'C', 'Mn', 'Si', 'P', 'S',
    # Thành phần hóa học mở rộng (Lấy từ kết quả phân tích phổ của phòng Lab)
    'Cu', 'Ni', 'Cr', 'Mo', 'V', 'Ti', 'Al', 'Ca', 'B', 'Nb', 'CEV', 'O', 'N', 'H'
]
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
        # 1. Lấy dữ liệu từ MySQL (Giữ nguyên logic cũ)
        ids_str = ",".join([f"'{str(x)}'" for x in chunk_ids])
        final_data_map = {} 
        slab_to_coils_map = {}

        try:
            conn_mysql = pymysql.connect(**current_db_conn, cursorclass=pymysql.cursors.DictCursor)
            with conn_mysql.cursor() as cursor:
                sql_cotinh = f"SELECT * FROM {current_view_cotinh} WHERE {COL_ID_CUON} IN ({ids_str})"
                cursor.execute(sql_cotinh)
                rows_cotinh = cursor.fetchall()
                target_slabs = set() 

                for r in rows_cotinh:
                    raw_coil_id = str(r[COL_ID_CUON])
                    coil_id = raw_coil_id.strip().upper()
                    if coil_id not in final_data_map: final_data_map[coil_id] = {}

                    if r.get('Yeild') is not None: final_data_map[coil_id]['YieldPoint'] = float(r['Yeild'])
                    if r.get('Tensile') is not None: final_data_map[coil_id]['Tensile'] = float(r['Tensile'])
                    if r.get('Elongation') is not None: final_data_map[coil_id]['Elongation'] = float(r['Elongation'])
                    if r.get('HRB') is not None: final_data_map[coil_id]['Hardness'] = float(r['HRB'])
                    if r.get('ImpactEnergy') is not None: 
                        final_data_map[coil_id]['ImpactEnergy'] = float(r['ImpactEnergy'])
                    if r.get('Loai'): 
                        final_data_map[coil_id]['AutoQuality'] = str(r.get('Loai')).strip().upper()
                    slab_id = r.get(COL_ID_PHOI_COTINH)
                    if slab_id:
                        slab_id = str(slab_id).strip()
                        target_slabs.add(slab_id)
                        if slab_id not in slab_to_coils_map: slab_to_coils_map[slab_id] = []
                        slab_to_coils_map[slab_id].append(coil_id)

                if target_slabs:
                    slabs_str = ",".join([f"'{str(x)}'" for x in target_slabs])
                    sql_tphh = f"SELECT * FROM {current_view_tphh} WHERE {COL_ID_PHOI_TPHH} IN ({slabs_str}) AND BilletSampleName = 'TSC9'"
                    cursor.execute(sql_tphh)
                    rows_tphh = cursor.fetchall()

                    for r in rows_tphh:
                        slab_id = str(r.get(COL_ID_PHOI_TPHH)).strip()
                        associated_coils = slab_to_coils_map.get(slab_id, [])
                        for coil_id in associated_coils:
                            tphh_elements = [
                                'C', 'Si', 'Mn', 'S', 'P', 'Cu', 'Ni', 'Cr', 'Mo', 
                                'V', 'Ti', 'Al', 'Ca', 'B', 'Nb', 'CEV', 'O', 'N', 'H'
                            ]
                            for el in tphh_elements:
                                if r.get(el) is not None:
                                    final_data_map[coil_id][el] = float(r[el])
            conn_mysql.close()
            
            # 2. LƯU VÀO DB LOCAL (CÓ SỬA ĐỔI ĐỂ BẢO TOÀN DỮ LIỆU CŨ)
            if final_data_map: 
                batch_save = []
                conn_local = None
                existing_rows = []
                try:
                    conn_local = db.get_connection()
                    clean_ids_found = list(final_data_map.keys())
                    placeholders = ','.join('?' * len(clean_ids_found))
                    
                    query = f"""
                        SELECT c.coil_id, c.raw_data, c.grade, c.scores, c.is_checked, c.quality_level, c.TARGET_LV2
                        FROM coil_data c WITH (NOLOCK) 
                        WHERE c.coil_id IN ({placeholders})
                        AND NOT EXISTS (
                            SELECT 1 
                            FROM sanluong sl WITH (NOLOCK) 
                            WHERE sl.[ID Cuộn bó] = c.coil_id 
                                AND sl.[Đã nhập kho] = N'Yes'
                        )
                    """
                    
                    cursor = conn_local.cursor()
                    cursor.execute(query, clean_ids_found)
                    existing_rows = db.fetchall_as_dict(cursor)
                except Exception as e:
                    print(f"Lỗi đọc DB local Prop: {e}")
                finally:
                    if conn_local:
                        conn_local.close()

                existing_map = {r['coil_id']: r for r in existing_rows}

                for cid, new_props in final_data_map.items():
                    curr = existing_map.get(cid, {})
                    if not curr:
                        continue
                    # Merge Raw Data
                    old_raw = json.loads(curr['raw_data']) if curr.get('raw_data') else {}
                    final_raw = old_raw.copy()
                    final_raw.update(new_props)
                    clean_raw = sanitize_data(final_raw)
                    
                    # Tính điểm tự động
                    curr_grade = curr.get('grade', 'SAE1006')
                    thickness_val = float(curr.get('TARGET_LV2') or 0.0)
                    new_auto_scores = process_coil_scores(cid, clean_raw, curr_grade,thickness_val)
                    
                    # --- LOGIC BẢO VỆ ĐIỂM (FINAL) ---
                    final_scores = new_auto_scores
                    if curr.get('is_checked') == 1:
                        old_scores_json = json.loads(curr['scores']) if curr.get('scores') else {}
                        final_scores = old_scores_json.copy()
                        
                        for k, v in new_auto_scores.items():
                            # 1. Nếu là Cơ tính/TPHH -> LUÔN CẬP NHẬT (Ghi đè cũ)
                            if k in MECH_KEYS and v > 0:
                                final_scores[k] = v
                            
                            # 2. Nếu là lỗi khác (Bề mặt...) -> CHỈ CẬP NHẬT NẾU TRƯỚC ĐÓ LÀ 0 (Trống)
                            # Dùng 'elif' để không chạy lại nếu đã update ở trên
                            elif old_scores_json.get(k, 0) == 0 and v > 0:
                                final_scores[k] = v
                            
                            # 3. Còn lại (cũ > 0) -> Giữ nguyên của User
                    curr_quality_level = curr.get('quality_level')
                    new_quality_level = new_props.get('AutoQuality')
                    
                    # Ưu tiên lấy từ MySQL (nếu có), nếu không có thì giữ nguyên đồ cũ (để không bị đè thành NULL)
                    final_quality = new_quality_level if new_quality_level else curr_quality_level
                    is_valid_existing_qual = False
                    if curr_quality_level:
                        curr_q_str = str(curr_quality_level).strip().upper()
                        if curr_q_str not in ['NONE', 'NULL', '', '0']:
                            is_valid_existing_qual = True
                    # Bảo vệ kết quả nếu User đã tick "is_checked" trên hệ thống Web
                    if curr.get('is_checked') == 1 and is_valid_existing_qual:
                        final_quality = curr_quality_level
                    item_to_save = {
                        'id': cid, 
                        'raw': clean_raw, 
                        'scores': final_scores,
                        'quality_level': final_quality
                    }
                    batch_save.append(item_to_save)

                if batch_save: 
                    db.update_mechanical_data(batch_save) 
                    updated_ids_list.extend([item['id'] for item in batch_save])
                    
        except Exception as e:
            print(f"Error sync prop: {e}")
            continue 

    return updated_ids_list
# Quét lại các cuộn gần nhất để bù đắp cơ tính
def rescan_recent_coils_for_mechanical():
    print("\n--- 🐢 BẮT ĐẦU QUÉT BÙ CƠ TÍNH")
    LOOKBACK_DAYS = 40
    for factory_id in FACTORY_CONFIGS:
        try:
            conn = None
            rows = []
            try:
                conn = db.get_connection()
                query = f"""
                    SELECT coil_id, raw_data, scores, quality_level, production_date , grade, TARGET_LV2
                    FROM coil_data WITH (NOLOCK) 
                    WHERE factory = ? 
                      AND production_date >= DATEADD(day, -{LOOKBACK_DAYS}, GETDATE())
                    ORDER BY production_date DESC
                """
                cursor = conn.cursor()
                cursor.execute(query, (factory_id,))
                rows = db.fetchall_as_dict(cursor)
            except Exception as e:
                print(f"❌ Lỗi truy vấn quét bù ({factory_id}): {str(e)}")
                continue 
            finally:
                if conn: 
                    conn.close()
                    
            if not rows:
                print("💤 Kho dữ liệu trống.")
                continue

            target_ids = []
            for r in rows:
                try:
                    # 1. Parse dữ liệu
                    scores = json.loads(r['scores']) if r['scores'] else {}
                    
                    # 2. Logic kiểm tra Cơ tính cơ bản (Kéo/Nén/Cứng)
                    has_base_mech = scores.get('YieldPoint') and scores.get('Hardness')
                    
                    # 3. Logic kiểm tra Va đập (ImpactEnergy)
                    # Nhờ scoring.py xử lý chuẩn, hễ ImpactEnergy = 0 nghĩa là cuộn này > 6mm và đang chờ Lab
                    missing_impact = ('ImpactEnergy' in scores and scores['ImpactEnergy'] == 0)

                    # 4. Cuộn thép thiếu cơ tính nếu rớt 1 trong 2 điều kiện
                    missing_mech = (not has_base_mech) or missing_impact
                    
                    # 3. Logic kiểm tra Cấp chất lượng
                    # Kiểm tra xem quality_level có dữ liệu chưa
                    q_val = str(r.get('quality_level', '')).strip().upper()
                    #missing_qual = (not q_val) or (q_val in ['NONE', 'NULL', '' , '0'])
                    # 4. Chỉ thêm vào danh sách nếu thiếu 1 trong 2
                    if missing_mech:
                        target_ids.append(r['coil_id'])
                        
                except:
                    target_ids.append(r['coil_id'])

            if not target_ids:
                print(f"✅ Nhà máy {factory_id}: ĐỦ điểm cơ tính.")
                continue

            print(f"🔍 Phát hiện {len(target_ids)} cuộn cần tính lại điểm cơ tính...")
            
            # Gọi hàm sync (Hàm này sẽ tự động lấy raw cũ + tính score mới + lưu đè an toàn)
            updated_ids = sync_properties_mysql(target_ids, factory_id)
            
            if updated_ids:
                count = len(updated_ids)
                if count <= 5:
                    id_str = ", ".join(updated_ids)
                    msg = f"[{factory_id}] Đã bù điểm cơ tính ({count}): {id_str}"
                else:
                    first_few = ", ".join(updated_ids[:3])
                    msg = f"[{factory_id}] Đã bù điểm cơ tính ({count}): {first_few}..."

        except Exception as e:
            print(f"❌ Lỗi Job Bù đắp ({factory_id}): {str(e)}")
        
    print("--- 🏁 KẾT THÚC QUÉT BÙ ---\n")
scheduler = BackgroundScheduler()
# Scheduler initialization
def init_scheduler():
    if not scheduler.running:
        scheduler.add_job(rescan_recent_coils_for_mechanical, trigger="interval", minutes=60, id='mechanical_catchup_job', replace_existing=True, next_run_time=datetime.now() + pd.Timedelta(minutes=1))
        scheduler.start()
        print("🚚 Khởi động luồng đẩy Nhiệt độ API...")
        threading.Thread(target=temp_api_worker, daemon=True).start()
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
        notify_frontend(final_msg, title="Auto Sync", factory_id=factory_id)

    except Exception as e:
        print(f"❌ Sync Error {target_id}: {e}")
        notify_frontend(f"Lỗi quét {target_id}: {str(e)}", title="Lỗi Hệ Thống")
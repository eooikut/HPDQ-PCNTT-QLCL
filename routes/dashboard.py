
from flask import Blueprint, app, render_template, current_app, request, jsonify
import pandas as pd
import threading
import json
import db  # Module db.py
import requests
from apscheduler.schedulers.background import BackgroundScheduler
import requests
from utils.common import sanitize_data, standardize_id
from utils.scoring import process_coil_scores,get_all_grade_configs,calculate_metric_surface,calculate_metric_value
from utils.sync_worker import sync_surface_defects, sync_properties_mysql,process_and_save_geometry,API_GEO_SINGLE_URL,process_coil_scores,LAST_DATA_UPDATE

dashboard_bp = Blueprint('dashboard_bp', __name__)
upload_lock = threading.Lock()

@dashboard_bp.route('/api/check_new_data', methods=['GET'])
def check_new_data():
    """API để Frontend polling: Hỏi xem có dữ liệu mới không"""
    # Lấy biến toàn cục từ sync_worker
    return jsonify(LAST_DATA_UPDATE)

@dashboard_bp.route('/qlcl', methods=['GET'])
def qlcl_page():
    return render_dashboard_logic()
@dashboard_bp.route('/upload_geometry', methods=['POST'])
def upload_geometry():
    """Upload Hình Học: Tính toán từ file Ket_qua_trung_nhau.xlsx"""
    with upload_lock:
        file = request.files.get('file')
        if not file: return jsonify({'msg': 'No file'})
        try:
            # 1. Đọc file (Hỗ trợ cả CSV và Excel)
            try:
                df = pd.read_csv(file) 
            except:
                file.seek(0)
                df = pd.read_excel(file, engine='calamine')

            # Chuẩn hóa tên cột (Viết hoa, xóa khoảng trắng)
            df.columns = (df.columns.astype(str)
                          .str.replace(r'[\n\r]+', ' ', regex=True) # Biến xuống dòng thành dấu cách
                          .str.replace(r'\s+', ' ', regex=True)     # Gộp nhiều dấu cách thành 1
                          .str.strip()
                          .str.upper())
            
            # 2. MAP CỘT THEO YÊU CẦU MỚI (Đã chuẩn hóa thành 1 dòng, viết hoa)
            rename_map = {
                'COIL_ID': 'CustomerID', 'L3 PIECE ID': 'CustomerID',
                'STEEL GRADE': 'Grade_Geo', 'MÃ MÁC THÉP': 'Grade_Geo',
                
                # Cột đo trực tiếp (Giữ nguyên logic cũ)
                'CROWN': 'Crown', 
                'WEDGE': 'Wedge', 
                'FLATNESS': 'Flatness', 'I-UNIT': 'Flatness',

                # --- [MAPPING MỚI CHO CÁC CỘT XUỐNG DÒNG] ---
                # MeasThk\n(mm) -> Sau khi chuẩn hóa sẽ thành "MEASTHK (MM)"
                'MEASTHK (MM)': 'Act_Thick', 
                
                # Targ Thk\n(mm) -> "TARG THK (MM)"
                'TARG THK (MM)': 'Tgt_Thick',
                
                # Meas Width\n(mm) -> "MEAS WIDTH (MM)"
                'MEAS WIDTH (MM)': 'Act_Width',
                
                # Targ Width\n(mm) -> "TARG WIDTH (MM)"
                'TARG WIDTH (MM)': 'Tgt_Width'
            }

            df.rename(columns=rename_map, inplace=True)
            df = standardize_id(df)

            batch_data = []
            conn = db.get_connection()
            existing_rows = conn.execute("SELECT coil_id, raw_data, grade, scores, is_checked FROM coil_data").fetchall()
            conn.close()
            existing_map = {r['coil_id']: {
                'raw': json.loads(r['raw_data']) if r['raw_data'] else {}, 
                'grade': r['grade'],
                'scores': json.loads(r['scores']) if r['scores'] else {},
                'is_checked': r['is_checked']
            } for r in existing_rows}

            count = 0
            for _, row in df.iterrows():
                if 'CustomerID' not in row or pd.isna(row['CustomerID']): continue
                coil_id = str(row['CustomerID']).strip()
                
                # 3. TÍNH TOÁN SAI LỆCH (DIFF)
                
                # ThickDiff = ABS(ACTUAL_THICK_F5 - TARGET_THICK)
                act_thick = pd.to_numeric(row.get('Act_Thick'), errors='coerce')
                tgt_thick = pd.to_numeric(row.get('Tgt_Thick'), errors='coerce')
                thick_diff = 0
                if pd.notnull(act_thick) and pd.notnull(tgt_thick):
                    thick_diff = abs(act_thick - tgt_thick)
                
                # WidthDiff = ABS(MEAS_WIDTH - TARGET_WIDTH)
                act_width = pd.to_numeric(row.get('Act_Width'), errors='coerce')
                tgt_width = pd.to_numeric(row.get('Tgt_Width'), errors='coerce')
                width_diff = 0
                if pd.notnull(act_width) and pd.notnull(tgt_width):
                    width_diff = abs(act_width - tgt_width)

                # 4. TẠO RAW DATA
                raw_map = {}
                
                # Lấy các cột đo trực tiếp nếu có trong file
                for k in ['Flatness', 'Crown', 'Wedge']:
                    if k in row: 
                        val = pd.to_numeric(row[k], errors='coerce')
                        if pd.notnull(val): raw_map[k] = val

                # Lưu thêm giá trị thực (nếu cần hiển thị chi tiết sau này)
                if pd.notnull(act_thick): raw_map['Thickness'] = act_thick
                if pd.notnull(act_width): raw_map['Width'] = act_width

                # Lưu kết quả tính toán vào đúng key Config
                raw_map['ThickDiff'] = thick_diff
                raw_map['WidthDiff'] = width_diff
                val_weight = pd.to_numeric(row.get('KhoiLuongPDI'), errors='coerce') # Cần đảm bảo file Excel có cột WEIGHT
                val_tgt_thick = tgt_thick # Đã lấy ở trên
                val_tgt_width = tgt_width
                clean_raw = sanitize_data(raw_map)

                # 5. Xử lý Mác thép (Ưu tiên giữ nguyên nếu DB đã có, nếu chưa thì lấy từ file này)
                current_info = existing_map.get(coil_id, {'raw': {}, 'grade': 'SAE1006'})
                final_grade = current_info['grade']
                
                excel_grade = str(row.get('Grade_Geo', '')).strip().upper()
                # Nếu trong DB đang là mặc định (SAE1006) mà file này có Grade xịn -> Cập nhật
                if final_grade == 'SAE1006' and excel_grade and excel_grade != 'NAN' and excel_grade != '':
                    final_grade = excel_grade

                # 6. Merge & Tính điểm
                full_raw = current_info['raw'].copy()
                full_raw.update(clean_raw)
                
                new_auto_scores = process_coil_scores(coil_id, full_raw, final_grade)
                
                # --- [SỬA 3]: LOGIC BẢO VỆ ĐIỂM SỐ ---
                final_scores = new_auto_scores
                if current_info.get('is_checked') == 1:
                    final_scores = current_info['scores'] # Giữ nguyên điểm cũ

                batch_data.append({
                    'id': coil_id,
                    'grade': final_grade, 
                    'raw': full_raw, # Lưu full raw đã merge
                    'scores': final_scores,
                    'is_checked': current_info.get('is_checked', 0),
                    'weight': float(val_weight) if pd.notnull(val_weight) else 0,
                    'target_thick': float(val_tgt_thick) if pd.notnull(val_tgt_thick) else 0,
                    'target_width': float(val_tgt_width) if pd.notnull(val_tgt_width) else 0
                })
                count += 1

            if batch_data: db.save_batch_coils_v2(batch_data)
            return jsonify({'msg': f'Upload Hình học OK! Đã cập nhật {count} cuộn.'})
            
        except Exception as e: return jsonify({'msg': str(e)})
@dashboard_bp.route('/upload_properties', methods=['POST'])
def upload_properties():
    with upload_lock:
        file = request.files.get('file')
        if not file: return jsonify({'msg': 'No file'})
        try:
            df = None
            # 1. CHIẾN THUẬT ĐỌC FILE MẠNH MẼ
            # Thử đọc là CSV trước
            try:
                df = pd.read_csv(file)
            except:
                file.seek(0)
                try:
                    # Thử đọc CSV với encoding utf-16 (Excel hay lưu dạng này)
                    df = pd.read_csv(file, encoding='utf-16', sep='\t')
                except:
                    file.seek(0)
                    # Cuối cùng thử đọc Excel (Dùng openpyxl cho phổ biến, header=None để tự dò)
                    df = pd.read_excel(file, header=None, engine='openpyxl')

            if df is None: return jsonify({'msg': 'Không thể đọc file. Hãy đảm bảo là file Excel hoặc CSV đúng chuẩn.'})

            # 2. TỰ ĐỘNG TÌM DÒNG TIÊU ĐỀ (HEADER)
            # Quét 10 dòng đầu để tìm dòng chứa chữ "ID" hoặc "Sản phẩm" hoặc "Mã mác thép"
            header_idx = -1
            for i, row in df.head(10).iterrows():
                # Chuyển cả dòng thành chuỗi in hoa để tìm
                row_str = " ".join([str(x).upper() for x in row.values])
                if 'ID' in row_str or 'SAN PHAM' in row_str or 'MA MAC THEP' in row_str:
                    header_idx = i
                    break
            
            # Nếu tìm thấy header thì set lại columns
            if header_idx != -1:
                df.columns = df.iloc[header_idx] # Lấy dòng đó làm tên cột
                df = df.iloc[header_idx+1:].reset_index(drop=True) # Lấy dữ liệu từ dòng sau đó
            
            # Chuẩn hóa tên cột
            df.columns = df.columns.astype(str).str.upper().str.replace('\n', ' ').str.strip()

            # 3. MAPPING CỘT (Bao gồm cả tên trong file CSV mới và Excel cũ)
            rename_map = {
                # Định danh
                'SẢN PHẨM': 'CustomerID', 'SAN PHAM': 'CustomerID', 'ID': 'CustomerID',
                'MÃ MÁC THÉP': 'Grade', 'MA MAC THEP': 'Grade', 'MÁC THÉP': 'Grade',
                
                # Cơ tính
                'G.H CHẢY': 'YieldPoint', 'G.H CHAY': 'YieldPoint', 'GIỚI HẠN CHẢY': 'YieldPoint',
                'G.H BỀN': 'Tensile', 'G.H BEN': 'Tensile', 'GIỚI HẠN BỀN': 'Tensile',
                'ĐỘ GIÃN DÀI': 'Elongation', 'DO GIAN DAI': 'Elongation',
                'ĐỘ CỨNG': 'Hardness', 'DO CUNG': 'Hardness',
                
                # Hóa học
                'C': 'C', 'MN': 'Mn', 'SI': 'Si', 'P': 'P', 'S': 'S'
            }
            df.rename(columns=rename_map, inplace=True)
            df = standardize_id(df)
            
            # --- XỬ LÝ DỮ LIỆU VÀO DB ---
            batch_data = []
            conn = db.get_connection()
            existing_rows = conn.execute("SELECT coil_id, raw_data, grade, scores, is_checked FROM coil_data").fetchall()
            conn.close()
            existing_map = {r['coil_id']: {
                'raw': json.loads(r['raw_data']) if r['raw_data'] else {}, 
                'grade': r['grade'],
                'scores': json.loads(r['scores']) if r['scores'] else {},
                'is_checked': r['is_checked']
            } for r in existing_rows}

            count = 0
            # Các cột cần lấy số liệu
            valid_keys = ['YieldPoint', 'Tensile', 'Elongation', 'Hardness', 'C', 'Mn', 'Si', 'P', 'S']

            for _, row in df.iterrows():
                if 'CustomerID' not in row: continue
                coil_id = str(row['CustomerID']).strip()
                if not coil_id or coil_id.upper() == 'NAN': continue
                
                new_grade = str(row.get('Grade', 'SAE1006')).strip().upper()
                if new_grade in ['NAN', '']: new_grade = 'SAE1006'
                
                raw_map = {}
                for k, v in row.to_dict().items():
                    if k in valid_keys:
                        val_str = str(v).strip().replace(',', '.')
                        try: raw_map[k] = float(val_str)
                        except: raw_map[k] = None
                
                clean_raw = sanitize_data(raw_map)
                
                # Lấy info cũ
                curr = existing_map.get(coil_id, {'raw': {}, 'grade': 'SAE1006', 'scores': {}, 'is_checked': 0})
                
                # Merge Raw Data
                final_raw = curr['raw'].copy()
                final_raw.update(clean_raw)
                
                # Tính điểm tự động
                new_auto_scores = process_coil_scores(coil_id, final_raw, new_grade)
                
                # --- [SỬA 3]: LOGIC BẢO VỆ ĐIỂM SỐ ---
                final_scores = new_auto_scores
                if curr.get('is_checked') == 1:
                    final_scores = curr['scores']
                
                batch_data.append({
                    'id': coil_id,
                    'grade': new_grade,
                    'raw': final_raw, # Lưu Full Raw
                    'scores': final_scores,
                    'is_checked': curr.get('is_checked', 0)
                })
                count += 1

            if batch_data: db.save_batch_coils(batch_data)
            return jsonify({'msg': f'Upload TPHH thành công! Đã cập nhật {count} cuộn.'})
            
        except Exception as e: return jsonify({'msg': f'Lỗi: {str(e)}'})
@dashboard_bp.route('/api/sync_single_coil', methods=['POST'])
# Manual scan single coil endpoint
def sync_single_coil_endpoint():
    try:
        req = request.json
        coil_id = str(req.get('coil_id', '')).strip()
        if not coil_id: return jsonify({'status': 'error', 'msg': 'Thiếu ID'})
        
        status_report = []

        # --- BƯỚC 1: HÌNH HỌC (Geometry) ---
        geo_found = False
        try:
            # Gọi API lấy data
            resp = requests.get(f"{API_GEO_SINGLE_URL}{coil_id}", timeout=5)
            if resp.status_code == 200:
                data = resp.json()
                rows = []
                if isinstance(data, list): rows = data
                elif isinstance(data, dict): rows = data.get('data') or data.get('rows') or []
                
                if rows:
                    # Gọi hàm lưu và kiểm tra kết quả
                    updated_ids = process_and_save_geometry(rows)
                    if updated_ids: 
                        geo_found = True
        except Exception as e:
            print(f"Geo Err: {e}")

        if geo_found: status_report.append("📐 Geo: ✅")
        else: status_report.append("📐 Geo: ❌")

        # --- BƯỚC 2: BỀ MẶT (Surface) ---
        try:
            # Hàm này giờ trả về số lượng (int)
            count = sync_surface_defects([coil_id])
            if count > 0: status_report.append("🔍 Surf: ✅")
            else: status_report.append("🔍 Surf: ❌ (Không có)")
        except: 
            status_report.append("🔍 Surf: ⚠️ Lỗi")

        # --- BƯỚC 3: CƠ/LÝ/HÓA (Properties) ---
        try:
            # Hàm này giờ trả về số lượng (int)
            count = sync_properties_mysql([coil_id])
            if count > 0: status_report.append("🧪 Prop: ✅")
            else: status_report.append("🧪 Prop: ❌ (Không có)")
        except Exception as e: 
            status_report.append(f"🧪 Prop: ⚠️ Lỗi ({str(e)})")

        # --- TỔNG KẾT ---
        final_msg = f"Kết quả quét {coil_id}: <br/>" + " | ".join(status_report)
        
        return jsonify({'status': 'success', 'msg': final_msg})

    except Exception as e:
        return jsonify({'status': 'error', 'msg': str(e)})
# Trong file dashboard.py

# Thêm import time nếu chưa có
import time

# API MỚI: QUÉT BATCH (NHIỀU CUỘN)
@dashboard_bp.route('/api/sync_batch_coils', methods=['POST'])
def sync_batch_coils_endpoint():
    try:
        req = request.json
        # Nhận chuỗi ID cách nhau bởi dấu phẩy hoặc xuống dòng
        raw_ids = req.get('coil_ids', '')
        # Tách chuỗi thành list, xóa khoảng trắng, loại bỏ rỗng
        coil_ids = [x.strip().upper() for x in raw_ids.replace('\n', ',').split(',') if x.strip()]
        
        if not coil_ids:
            return jsonify({'status': 'error', 'msg': 'Danh sách ID trống!'})
        
        if len(coil_ids) > 100:
            return jsonify({'status': 'error', 'msg': 'Chỉ nên quét tối đa 100 cuộn/lần để đảm bảo hiệu năng.'})

        # CHẠY NGẦM (THREADING) ĐỂ KHÔNG TREO UI
        def run_batch_job(target_ids):
            print(f"🚀 [Batch Scan] Bắt đầu quét {len(target_ids)} cuộn...")
            
            # 1. Quét Cơ Lý (MySQL) - Nhanh nhất chạy trước
            # Hàm này đã hỗ trợ list ID, chạy 1 lệnh SQL IN (...)
            try:
                sync_properties_mysql(target_ids)
            except Exception as e:
                print(f"❌ [Batch Prop Error] {e}")

            # 2. Quét API (Cần loop) - Hình học & Bề mặt
            # Vì API bề mặt và Hình học lẻ phải gọi từng cái, ta loop ở đây
            for idx, cid in enumerate(target_ids):
                try:
                    # A. Hình học (Gọi API lẻ)
                    geo_resp = requests.get(f"{API_GEO_SINGLE_URL}{cid}", timeout=3)
                    if geo_resp.status_code == 200:
                        data = geo_resp.json()
                        rows = []
                        if isinstance(data, list): rows = data
                        elif isinstance(data, dict): rows = data.get('data', [])
                        if rows: process_and_save_geometry(rows)
                    
                    # B. Bề mặt (Gọi hàm sync có sẵn)
                    # Hàm sync_surface_defects nhận list, nhưng ta truyền [cid] để kiểm soát delay
                    sync_surface_defects([cid])
                    
                    # --- RATE LIMIT CONTROL ---
                    # Ngủ 0.2 giây giữa các lần gọi để không làm sập API bên kia
                    time.sleep(0.2) 
                    
                except Exception as e:
                    print(f"⚠️ Lỗi quét cuộn {cid}: {e}")
            
            print(f"🏁 [Batch Scan] Hoàn tất {len(target_ids)} cuộn.")

        # Khởi động luồng chạy ngầm
        thread = threading.Thread(target=run_batch_job, args=(coil_ids,))
        thread.start()

        return jsonify({
            'status': 'success', 
            'msg': f'Đã tiếp nhận {len(coil_ids)} cuộn. Hệ thống đang xử lý ngầm, vui lòng reload trang sau vài phút.'
        })

    except Exception as e:
        return jsonify({'status': 'error', 'msg': str(e)})
## RENDER HEATMAP 
def get_menu_structure_for_grade(grade_config):
    menu = {'surface': [], 'geometry': [], 'prop': []}
    if not grade_config: return menu
    for name, cfg in grade_config.items():
        grp = cfg.get('group')
        if grp == 'surface': menu['surface'].append(name)
        elif grp == 'geometry': menu['geometry'].append(name)
        elif grp in ['mechanical', 'chemical']: menu['prop'].append(name)
    return menu


def render_dashboard_logic(msg=None):
    conn = db.get_connection()
    rows = conn.execute("SELECT * FROM coil_data").fetchall()
    conn.close()
    all_data = {r['coil_id']: {'scores': json.loads(r['scores']) if r['scores'] else {}, 'raw_data': json.loads(r['raw_data']) if r['raw_data'] else {}, 'GRADE': r['grade'], 'IS_CHECKED': r['is_checked']} for r in rows}
    selected_grade = request.args.get('grade', 'SAE1006')
    dashboard_data = regenerate_dashboard_data(all_data, selected_grade)
    
    data_wrapper = {
        'has_data': bool(all_data),
        'time_range': db.get_config('time_range', ''),
        'radar_data': dashboard_data['radar_data'],
        'tabs': dashboard_data['tabs'],
    }
    return render_template('qlcl.html', data=data_wrapper, radar_data=data_wrapper['radar_data'], menu=dashboard_data['menu'], current_grade=selected_grade, msg=msg)
# Regenerate dashboard data based on selected grade
def regenerate_dashboard_data(all_data, selected_grade):
    all_configs = get_all_grade_configs()
    # current_config = all_configs.get(selected_grade, all_configs.get('SAE1006'))
    if selected_grade == 'ALL':
        current_config = all_configs.get('SAE1006')
    else:
        current_config = all_configs.get(selected_grade, all_configs.get('SAE1006'))
    final_radar_data = {} # Dữ liệu gửi xuống Frontend (Chứa TOÀN BỘ cuộn)
    target_coils = []     # Dữ liệu để tính toán Tabs thống kê (Chỉ Mác đang chọn)

    # 1. DUYỆT QUA TẤT CẢ CUỘN (Không lọc ngay đầu để tránh mất dữ liệu tìm kiếm)
    for cid, d in all_data.items():
        raw = d.get('raw_data', {})
        current_scores = d.get('scores', {})
        # Lấy grade của cuộn, nếu không có thì mặc định
        db_grade = d.get('GRADE') if d.get('GRADE') else 'SAE1006'

        # --- A. TÍNH ĐIỂM AUTO (Reference Line) ---
        # Tính điểm máy cho TẤT CẢ các cuộn để hiển thị đúng khi xem chi tiết
        db_grade_clean = str(db_grade).strip().upper()

        # Tính toán lại điểm (nếu cần)
        auto_scores = process_coil_scores(cid, raw, db_grade_clean)

        # --- B. TẠO CẤU TRÚC PHẲNG (FLAT STRUCTURE) ---
        # [QUAN TRỌNG]: Copy điểm số ra lớp ngoài cùng để JS cũ không bị lỗi
        frontend_obj = current_scores.copy() 
        
        # Gắn thêm dữ liệu phụ trợ vào object này
        frontend_obj['auto_scores'] = auto_scores  # <--- Dữ liệu gốc cho Radar mới
        frontend_obj['raw_data'] = raw
        frontend_obj['GRADE'] = db_grade_clean
        frontend_obj['IS_CHECKED'] = d.get('IS_CHECKED', False)

        # Lưu vào danh sách tổng
        final_radar_data[cid] = frontend_obj

        # --- C. LỌC ĐỂ TÍNH TOÁN TAB (Chỉ tính thống kê cho Mác đang chọn) ---
        if selected_grade == 'ALL' or db_grade_clean == selected_grade:
            target_coils.append({
                'CustomerID': cid, 
                'Raw': raw,
                'Scores': current_scores,
                'Grade': db_grade_clean # Lưu lại Grade gốc của cuộn
            })
    
    # Nếu không có cuộn nào thuộc Mác này, trả về tabs rỗng nhưng VẪN TRẢ radar_data (để Search vẫn thấy cuộn khác)
    if not target_coils:
        return {
            'tabs': {}, 
            'radar_data': final_radar_data, 
            'menu': get_menu_structure_for_grade(current_config)
        }

    # --- PHẦN TÍNH TOÁN TABS (Giữ nguyên logic cũ) ---
    score_lookup = {item['CustomerID']: item['Scores'] for item in target_coils}

    flattened_data = []
    surface_rows = []
    
    for item in target_coils:
        row_main = {'CustomerID': item['CustomerID']}
        item_grade = item.get('Grade', 'SAE1006')
        item_config = all_configs.get(item_grade, all_configs.get('SAE1006'))
        if item['Raw']:
            for k, v in item['Raw'].items():
                row_main[k] = v 
                
                cfg_item = item_config.get(k, {}) 
                # Nếu không tìm thấy trong config gốc, thử tìm trong config SAE1006 (fallback)
                if not cfg_item: cfg_item = current_config.get(k, {})

                is_surface_mode = cfg_item.get('mode') in ['count', 'matrix']
                is_surface_group = cfg_item.get('group') == 'surface'
                
                # 2. Chỉ cần nó là lỗi bề mặt (theo định nghĩa chung) thì lấy
                # Và quan trọng: Key k phải tồn tại trong current_config (SAE1006) để có Tab hiển thị
                if k in current_config and (is_surface_mode or is_surface_group):
                    if isinstance(v, list):
                        for s in v: 
                            surface_rows.append({'CustomerID': item['CustomerID'], 'DefectClass': k, 'Size': s})
                    else:
                        try:
                            val_int = int(v)
                            if val_int > 0:
                                for _ in range(val_int): 
                                    surface_rows.append({'CustomerID': item['CustomerID'], 'DefectClass': k, 'Size': 0})
                        except: pass
                        
        flattened_data.append(row_main)
    
    df_main = pd.DataFrame(flattened_data)
    df_surface = pd.DataFrame(surface_rows) if surface_rows else pd.DataFrame(columns=['CustomerID', 'DefectClass', 'Size'])

    tabs_data = {}
    total_rolls = len(target_coils)
    
    for name, cfg in current_config.items():
        if cfg.get('group') == 'surface':
            tabs_data[name] = calculate_metric_surface(df_surface, name, cfg, total_rolls)
        else:
            tabs_data[name] = calculate_metric_value(df_main, name, cfg, total_rolls, score_lookup)

    return {'tabs': tabs_data, 'radar_data': final_radar_data, 'menu': get_menu_structure_for_grade(current_config)}


@dashboard_bp.route('/qlcl', methods=['POST'])
def upload_surface():
    """Upload Bề Mặt -> Render Dashboard"""
    with upload_lock:
        file = request.files.get('file')
        if not file: return render_dashboard_logic(msg='Chưa chọn file')
        try:
            df = pd.read_excel(file,sheet_name=0, engine='calamine')
            df.rename(columns={'Cuộn': 'CustomerID', 'Kích thước': 'Size', 'Lỗi': 'DefectClass'}, inplace=True)
            df = standardize_id(df)
            df['Size'] = pd.to_numeric(df['Size'], errors='coerce').fillna(0)

            batch_data = []
            conn = db.get_connection()
            existing_rows = conn.execute("SELECT coil_id, raw_data, grade, scores, is_checked FROM coil_data").fetchall()
            conn.close()
            existing_map = {r['coil_id']: {'raw': json.loads(r['raw_data']) if r['raw_data'] else {}, 'grade': r['grade']} for r in existing_rows}

            grouped = df.groupby('CustomerID')
            for coil_id, group in grouped:
                raw_map = {}
                for defect_type, defect_group in group.groupby('DefectClass'):
                    sizes = defect_group['Size'].tolist()
                    raw_map[defect_type] = sizes 
                
                clean_raw = sanitize_data(raw_map)
                
                current_info = existing_map.get(coil_id, {'raw': {}, 'grade': 'SAE1006'})
                full_raw = current_info['raw'].copy()
                full_raw.update(clean_raw)
                new_auto_scores = process_coil_scores(coil_id, full_raw, current_info['grade'])
                final_scores = new_auto_scores
                if current_info.get('is_checked') == 1:
                    final_scores = current_info['scores'] # Giữ điểm cũ

                batch_data.append({
                    'id': coil_id, 
                    'grade': None, 
                    'raw': clean_raw, 
                    'scores': final_scores,
                    'is_checked': current_info.get('is_checked', 0)
                })

            if batch_data: db.save_batch_coils(batch_data)

            return render_dashboard_logic(msg=f'Upload Bề mặt thành công! Đã xử lý {len(batch_data)} cuộn.')
        except Exception as e: return render_dashboard_logic(msg=f'Lỗi: {str(e)}')
     

## Nhập tay
@dashboard_bp.route('/get_manual_config', methods=['GET'])
def get_manual_config():
    return jsonify({
        'SURFACE_MANUAL': [{'id': 'oil', 'label': 'Gấp nếp'}, {'id': 'rust', 'label': 'Nếp Nhăn'}, {'id': 'scratch_m', 'label': 'Vết Hằn'}, {'id': 'dirt', 'label': 'Gãy mặt'}, {'id': 'mark', 'label': 'Xỉ thứ cấp'}, {'id': 'scale', 'label': 'Xỉ cán'}, {'id': 'other_s', 'label': 'Xỉ muối tiêu'}],
        'GEO_MANUAL': [{'id': 'telescope', 'label': 'Cong cạnh'}],
        'APPEARANCE': [{'id': 'strap', 'label': 'Khuyết biên'}, {'id': 'label_tag', 'label': 'Bava biên'}, {'id': 'packaging', 'label': 'Vỡ biên'}, {'id': 'edge_cond', 'label': 'Sổ vòng'}, {'id': 'coil_shape', 'label': 'Loa cuộn'}]
    })
# API LƯU ĐIỂM ĐÁNH GIÁ THỦ CÔNG VÀ GHI LOG
@dashboard_bp.route('/save_manual_data', methods=['POST'])
def save_manual_data():
    try:
        req = request.json
        coil_id = req.get('coil_id')
        new_scores = req.get('scores')
        user_name = req.get('user', 'User')

        if not coil_id: return jsonify({'status':'error', 'msg': 'Thiếu ID cuộn'})

        conn = db.get_connection() # <--- Kết nối 1 mở tại đây
        
        try: # Thêm try/finally để chắc chắn đóng conn
            # 1. Lấy dữ liệu CŨ từ DB
            curr_row = conn.execute("SELECT scores FROM coil_data WHERE coil_id=?", (coil_id,)).fetchone()
            old_scores = json.loads(curr_row['scores']) if curr_row and curr_row['scores'] else {}

            # 2. So sánh và chuẩn bị Log
            logs = []
            import datetime
            now = datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")

            for key, new_val in new_scores.items():
                old_val = old_scores.get(key, 0)
                if float(new_val) != float(old_val):
                    logs.append((coil_id, user_name, key, float(old_val), float(new_val), now))

            if logs:
                conn.executemany("INSERT INTO audit_log (coil_id, user_name, defect_key, old_value, new_value, changed_at) VALUES (?, ?, ?, ?, ?, ?)", logs)

            

            final_scores = old_scores.copy()
            final_scores.update(new_scores)

            conn.execute(
                "UPDATE coil_data SET scores = ?, is_checked = 1 WHERE coil_id = ?", 
                (json.dumps(final_scores), coil_id)
            )
            
            conn.commit() 
            return jsonify({'status': 'success', 'msg': f'Đã lưu và ghi nhận {len(logs)} thay đổi!'})

        except Exception as e:
            conn.rollback() 
            raise e
        finally:
            conn.close() 

    except Exception as e: 
        return jsonify({'status':'error', 'msg':str(e)})
@dashboard_bp.route('/api/init_log_table', methods=['GET'])
def init_log_table():
    try:
        conn = db.get_connection()
        # 1. Tạo bảng nếu chưa có
        conn.execute("""
            CREATE TABLE IF NOT EXISTS system_logs (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                title TEXT,
                message TEXT,
                log_type TEXT,
                is_read INTEGER DEFAULT 0,  -- Cột mới: 0=Chưa đọc, 1=Đã đọc
                created_at TEXT
            )
        """)
        
        # 2. Migration: Nếu bảng đã có từ trước mà thiếu cột is_read thì thêm vào
        try:
            conn.execute("ALTER TABLE system_logs ADD COLUMN is_read INTEGER DEFAULT 0")
        except:
            pass # Cột đã tồn tại, bỏ qua

        conn.commit()
        conn.close()
        return jsonify({'status': 'success', 'msg': 'DB Logs Ready!'})
    except Exception as e:
        return jsonify({'status': 'error', 'msg': str(e)})
@dashboard_bp.route('/api/mark_all_read', methods=['POST'])
def mark_all_read():
    """Đánh dấu tất cả là đã đọc khi bấm vào chuông"""
    try:
        conn = db.get_connection()
        conn.execute("UPDATE system_logs SET is_read = 1 WHERE is_read = 0")
        conn.commit()
        conn.close()
        return jsonify({'status': 'success'})
    except Exception as e:
        return jsonify({'status': 'error'})
@dashboard_bp.route('/api/get_unread_count', methods=['GET'])
def get_unread_count():
    """Đếm số thông báo chưa đọc"""
    try:
        conn = db.get_connection()
        row = conn.execute("SELECT COUNT(*) as cnt FROM system_logs WHERE is_read = 0").fetchone()
        conn.close()
        return jsonify({'count': row['cnt']})
    except:
        return jsonify({'count': 0})
# 2. API LẤY LỊCH SỬ THÔNG BÁO
@dashboard_bp.route('/api/get_system_logs', methods=['GET'])
def get_system_logs():
    try:
        conn = db.get_connection()
        # Lấy 50 thông báo gần nhất
        rows = conn.execute("SELECT * FROM system_logs ORDER BY id DESC LIMIT 50").fetchall()
        conn.close()
        
        logs = []
        for r in rows:
            logs.append({
                'id': r['id'],
                'title': r['title'],
                'message': r['message'],
                'type': r['log_type'],
                'time': r['created_at']
            })
        return jsonify(logs)
    except Exception as e:
        return jsonify([])

# Hàm nội bộ để các file khác gọi (Lưu log vào DB)
def log_system_event(title, message, log_type='info'):
    try:
        import datetime
        now_str = datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        
        conn = db.get_connection()
        
        # [QUAN TRỌNG]: Kiểm tra xem tin nhắn y hệt này đã xuất hiện trong 30 giây qua chưa?
        # Nếu có rồi thì KHÔNG GHI NỮA (Chống Spam)
        check_sql = """
            SELECT id FROM system_logs 
            WHERE message = ? 
            ORDER BY id DESC LIMIT 1
        """
        existing = conn.execute(check_sql, (message,)).fetchone()
        
        should_insert = True
        if existing:
            pass 
        last_log = conn.execute("SELECT message, created_at FROM system_logs ORDER BY id DESC LIMIT 1").fetchone()
        
        if last_log and last_log['message'] == message:
            # Tính khoảng cách thời gian
            last_time = datetime.datetime.strptime(last_log['created_at'], "%Y-%m-%d %H:%M:%S")
            now_time = datetime.datetime.now()
            diff = (now_time - last_time).total_seconds()
            
            if diff < 60: # Nếu trùng nội dung trong vòng 60 giây -> KHÔNG LƯU
                conn.close()
                print(f"♻️ [Anti-Spam] Bỏ qua log trùng: {message}")
                return

        # Nếu không trùng hoặc đã quá 60s -> Lưu mới
        conn.execute(
            "INSERT INTO system_logs (title, message, log_type, is_read, created_at) VALUES (?, ?, ?, 0, ?)",
            (title, message, log_type, now_str)
        )
        conn.commit()
        conn.close()
    except Exception as e:
        print(f"❌ Lỗi ghi log: {e}")
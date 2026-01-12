
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
from utils.sync_worker import sync_surface_defects, sync_properties_mysql,process_and_save_geometry,API_GEO_SINGLE_URL,process_coil_scores,LAST_DATA_UPDATE, FACTORY_CONFIGS
import time
dashboard_bp = Blueprint('dashboard_bp', __name__)
upload_lock = threading.Lock()
@dashboard_bp.route('/api/smart_resync_surface', methods=['GET', 'POST'])
def smart_resync_surface():
    try:
        # 1. Lấy thêm cột 'factory' từ DB
        conn = db.get_connection()
        cursor = conn.cursor()
        query = "SELECT coil_id, raw_data, factory FROM coil_data WITH (NOLOCK)"
        cursor.execute(query)
        rows = db.fetchall_as_dict(cursor) 
        conn.close()
        # 2. Phân loại cuộn theo nhà máy
        missing_map = {fid: [] for fid in FACTORY_CONFIGS}
        
        SURFACE_KEYS = ['MI', 'HPrScale', 'HOLE', 'RIP', 'BRUS', 'LC', 'SCRT', 'EL']

        for r in rows:
            raw_val = r['raw_data'] 
            factory_val = r['factory']
            coil_id = r['coil_id']
            raw_json = json.loads(raw_val) if raw_val else {}
            has_surface = any(k in raw_json for k in SURFACE_KEYS)
            
            if not has_surface:
                fid = factory_val if factory_val else 'HRC1'
                if fid in missing_map:
                    missing_map[fid].append(coil_id)

        # 3. Chạy vòng lặp quét bù cho từng nhà máy
        msg_details = []
        for fid, ids in missing_map.items():
            if ids:
                print(f"🚑 [Smart Resync - {fid}] Quét bù {len(ids)} cuộn...")
                # GỌI HÀM VỚI THAM SỐ FACTORY_ID
                sync_surface_defects(ids, factory_id=fid) 
                msg_details.append(f"{fid}: {len(ids)} cuộn")

        if not msg_details:
            return jsonify({'status': 'success', 'msg': 'Dữ liệu bề mặt đã đầy đủ.'})

        return jsonify({
            'status': 'success', 
            'msg': f"Đã quét bù: {', '.join(msg_details)}"
        })

    except Exception as e:
        return jsonify({'status': 'error', 'msg': str(e)})
@dashboard_bp.route('/api/backfill_geo_info', methods=['GET'])
def backfill_geo_info():
    try:
        conn = db.get_connection()
        cursor = conn.cursor()
        # [QUAN TRỌNG] Lấy thêm cột factory
        cursor.execute("SELECT coil_id, production_date, slab_grade, factory FROM coil_data WITH (NOLOCK)") 
        rows = db.fetchall_as_dict(cursor)
        conn.close()
        # Lọc ra các cuộn thiếu thông tin
        target_items = []
        for r in rows:
            if not r['production_date'] or not r['slab_grade']:
                target_items.append({
                    'id': r['coil_id'],
                    'factory': r.get('factory', 'HRC1') # Lấy factory, mặc định HRC1
                })
        if not target_items:
            return jsonify({'status': 'success', 'msg': 'Dữ liệu đã đầy đủ.'})

        def run_backfill_job(items):
            print(f"🐢 [Backfill] Bắt đầu quét bù {len(items)} cuộn...")
            
            for item in items:
                cid = item['id']
                fid = item['factory']
                
                try:
                    cfg = FACTORY_CONFIGS.get(fid)
                    if not cfg: continue
                    api_url = f"{cfg['api_geo']}{cid}" 
                    
                    resp = requests.get(api_url, timeout=3)
                    if resp.status_code == 200:
                        data = resp.json()
                        rows_data = []
                        if isinstance(data, list): rows_data = data
                        elif isinstance(data, dict): rows_data = data.get('data', [])
                        
                        if rows_data:
                            process_and_save_geometry(rows_data, factory_id=fid)
                    
                    time.sleep(0.1)
                except Exception as e:
                    print(f"⚠️ Err {cid}: {e}")

        threading.Thread(target=run_backfill_job, args=(target_items,)).start()

        return jsonify({'status': 'success', 'msg': f'Đang chạy ngầm cập nhật {len(target_items)} cuộn...'})

    except Exception as e:
        return jsonify({'status': 'error', 'msg': str(e)})

@dashboard_bp.route('/api/fix_stuck_scores', methods=['GET'])
def fix_stuck_scores():
    """
    API chạy 1 lần để sửa lỗi: Raw có dữ liệu nhưng Score = 0 do bị is_checked chặn.
    Logic: Chỉ cập nhật nếu điểm cũ = 0. Giữ nguyên nếu điểm cũ > 0 (đã chấm tay).
    """
    try:
        conn = db.get_connection()
        cursor = conn.cursor()
        cursor.execute("SELECT coil_id, raw_data, grade, scores, is_checked FROM coil_data WITH (NOLOCK) WHERE is_checked = 1")
        rows = db.fetchall_as_dict(cursor) # <--- SỬA
        conn.close()

        updated_count = 0
        batch_update = []

        for r in rows:
            coil_id = r['coil_id']
            # Parse dữ liệu
            raw = json.loads(r['raw_data']) if r['raw_data'] else {}
            old_scores = json.loads(r['scores']) if r['scores'] else {}
            grade = r['grade']

            # Tính toán lại điểm số dựa trên Raw hiện tại
            new_auto_scores = process_coil_scores(coil_id, raw, grade)

            has_change = False
            final_scores = old_scores.copy()

            # --- LOGIC CỐT LÕI ---
            for key, new_val in new_auto_scores.items():
                old_val = old_scores.get(key, 0)
                
                # CHỈ CẬP NHẬT KHI: Điểm cũ là 0 (hoặc thiếu) VÀ Điểm mới có giá trị (>0)
                # Ví dụ: Yield cũ = 0, Yield mới = 6 => CẬP NHẬT
                if old_val == 0 and new_val > 0:
                    final_scores[key] = new_val
                    has_change = True
            if has_change:
                batch_update.append({
                    'id': coil_id,
                    'grade': grade,
                    'raw': raw,
                    'scores': final_scores,
                    'is_checked': 1,
                    'factory': r.get('factory', 'HRC1') 
                })
                updated_count += 1

        # Lưu lại vào DB
        if batch_update:
            db.save_batch_coils_v2(batch_update)

        return jsonify({
            'status': 'success', 
            'msg': f'Đã rà soát {len(rows)} cuộn khóa. Đã sửa lỗi điểm số cho {updated_count} cuộn.'
        })

    except Exception as e:
        return jsonify({'status': 'error', 'msg': str(e)})
@dashboard_bp.route('/api/check_new_data', methods=['GET'])
def check_new_data():
    """API để Frontend polling: Hỏi xem có dữ liệu mới không"""
    return jsonify(LAST_DATA_UPDATE)

@dashboard_bp.route('/qlcl', methods=['GET'])
def qlcl_page():
    return render_dashboard_logic()

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
            updated_list = sync_properties_mysql([coil_id])
            
            if len(updated_list) > 0: # <--- Sửa logic check tại đây
                status_report.append("🧪 Prop: ✅")
            else: 
                status_report.append("🧪 Prop: ❌ (Không có)")
        except Exception as e: 
            status_report.append(f"🧪 Prop: ⚠️ Lỗi ({str(e)})")

        # --- TỔNG KẾT ---
        final_msg = f"Kết quả quét {coil_id}: <br/>" + " | ".join(status_report)
        
        return jsonify({'status': 'success', 'msg': final_msg})

    except Exception as e:
        return jsonify({'status': 'error', 'msg': str(e)})

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
    current_factory = request.args.get('factory', 'HRC1') # <--- MỚI
    selected_grade = request.args.get('grade', 'ALL')

    start_date = request.args.get('start_date', '')
    end_date = request.args.get('end_date', '')

    conn = db.get_connection()
    cursor = conn.cursor()
    sql = """
        SELECT coil_id, grade, raw_data, scores, is_checked, 
               production_date, updated_at, factory ,
               Temperature, Speed, quality_level        
        FROM coil_data WITH (NOLOCK) 
        WHERE factory = ? 
    """
    params = [current_factory]

    if selected_grade != 'ALL':
        sql += " AND grade = ?"
        params.append(selected_grade)
    # 2. Nếu có lọc Ngày bắt đầu
    if start_date:
        sql += " AND production_date >= ?"
        # Thêm giờ bắt đầu 00:00:00
        params.append(f"{start_date} 00:00:00")

    # 3. Nếu có lọc Ngày kết thúc
    if end_date:
        sql += " AND production_date <= ?"
        # Thêm giờ kết thúc 23:59:59 để lấy trọn ngày
        params.append(f"{end_date} 23:59:59.999")

    sql += " ORDER BY production_date DESC, coil_id DESC"
    
    cursor.execute(sql, tuple(params))
    rows = db.fetchall_as_dict(cursor) 
    conn.close()
    all_data = {
        r['coil_id']: {
            'scores': json.loads(r['scores']) if r['scores'] else {}, 
            'raw_data': json.loads(r['raw_data']) if r['raw_data'] else {}, 
            'GRADE': r['grade'], 
            'IS_CHECKED': r['is_checked'],
            'updated_at': r['updated_at'],
            'production_date': str(r['production_date']) if r['production_date'] else '',
            'Temperature': r['Temperature'] if r['Temperature'] else 0,
            'Speed': r['Speed'] if r['Speed'] else 0,
            'quality_level': r['quality_level'] if r['quality_level'] else ''
        } 
        for r in rows
    }
    # selected_grade = request.args.get('grade', 'SAE1006')
    dashboard_data = regenerate_dashboard_data(all_data, selected_grade)
    
    data_wrapper = {
        'has_data': bool(all_data),
        'time_range': db.get_config('time_range', ''),
        'radar_data': dashboard_data['radar_data'],
        'tabs': dashboard_data['tabs'],
    }
    return render_template('qlcl.html', 
            data=data_wrapper, 
            radar_data=data_wrapper['radar_data'], 
            menu=dashboard_data['menu'], 
            current_grade=selected_grade,
            current_factory=current_factory,
            start_date=start_date,
            end_date=end_date,
            msg=msg
        )
def regenerate_dashboard_data(all_data, selected_grade):
    all_configs = get_all_grade_configs()
    current_config = all_configs.get(selected_grade)
    if not current_config:
        current_config = all_configs.get('SAE1006')
    final_radar_data = {} # Dữ liệu gửi xuống Frontend (Chứa TOÀN BỘ cuộn)
    target_coils = []     # Dữ liệu để tính toán Tabs thống kê (Chỉ Mác đang chọn)

    # 1. DUYỆT QUA TẤT CẢ CUỘN (Không lọc ngay đầu để tránh mất dữ liệu tìm kiếm)
    for cid, d in all_data.items():
        raw = d.get('raw_data', {})
        current_scores = d.get('scores', {})
        db_grade = d.get('GRADE') if d.get('GRADE') else 'SAE1006'
        db_grade_clean = str(db_grade).strip().upper()

        if raw:
             auto_scores = process_coil_scores(cid, raw, db_grade_clean, cached_config=all_configs)
        else:
             auto_scores = {}
        frontend_obj = current_scores.copy() 
        
        frontend_obj['auto_scores'] = auto_scores
        optimized_raw = {}
        if raw:
            for k, v in raw.items():
                if isinstance(v, list):
                    cnt = len(v)
                    if cnt > 0:
                        try:
                            mx = max([float(x) for x in v if x is not None and x != ''])
                            optimized_raw[k] = f"SL: {cnt} (Max: {mx:.2f})"
                        except:
                            optimized_raw[k] = f"SL: {cnt}"
                    else:
                        # Giữ cho nhẹ JSON
                        pass 
                else:
                    optimized_raw[k] = v
        
        frontend_obj['raw_data'] = optimized_raw
        frontend_obj['GRADE'] = db_grade_clean
        frontend_obj['IS_CHECKED'] = d.get('IS_CHECKED', False)
        prod_date = d.get('production_date', '')
        frontend_obj['production_date'] = str(prod_date) if prod_date else ''
        frontend_obj['Temperature'] = d.get('Temperature', 0)
        frontend_obj['Speed'] = d.get('Speed', 0)
        frontend_obj['quality_level'] = d.get('quality_level', '')
        final_radar_data[cid] = frontend_obj
        # --- C. LỌC ĐỂ TÍNH TOÁN TAB (Chỉ tính thống kê cho Mác đang chọn) ---
        if selected_grade == 'ALL' or db_grade_clean == selected_grade:
            target_coils.append({
                'CustomerID': cid, 
                'Raw': raw,
                'Scores': current_scores,
                'Grade': db_grade_clean 
            })
    
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
                if not cfg_item: cfg_item = current_config.get(k, {})
                is_surface_mode = cfg_item.get('mode') in ['count', 'matrix']
                is_surface_group = cfg_item.get('group') == 'surface'
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

@dashboard_bp.route('/api/recalc_scores_by_grade', methods=['POST'])
def recalc_scores_by_grade():
    try:
        req = request.json
        target_grade = req.get('grade')
        
        if not target_grade: return jsonify({'status': 'error', 'msg': 'Thiếu tên Mác thép'})

        print(f"🔄 Đang tính lại điểm cho toàn bộ cuộn thuộc mác {target_grade}...")

        conn = db.get_connection()
        cursor = conn.cursor()
        
        # [SỬA 1]: Thêm các cột production_date, slab_grade, weight... vào câu SELECT
        query = """
            SELECT coil_id, raw_data, grade, scores, is_checked, factory,
                   production_date, slab_grade, weight, target_thick, target_width
            FROM coil_data WITH (NOLOCK) 
            WHERE grade = ?
        """
        cursor.execute(query, (target_grade,))
        rows = db.fetchall_as_dict(cursor)
        conn.close()

        if not rows:
            return jsonify({'status': 'success', 'msg': f'Không tìm thấy cuộn nào thuộc mác {target_grade}.'})

        batch_update = []
        count = 0

        for r in rows:
            coil_id = r['coil_id']
            raw = json.loads(r['raw_data']) if r['raw_data'] else {}
            old_scores = json.loads(r['scores']) if r['scores'] else {}
            
            new_scores = process_coil_scores(coil_id, raw, target_grade)
            
            final_scores = new_scores
            if r['is_checked'] == 1:
                final_scores = old_scores.copy()
                for k, v in new_scores.items():
                    if old_scores.get(k, 0) == 0:
                        final_scores[k] = v
            batch_update.append({
                'id': coil_id,
                'grade': target_grade,
                'raw': raw,
                'scores': final_scores, 
                'is_checked': r['is_checked'],
                'factory': r.get('factory', 'HRC1'),
                'production_date': r.get('production_date'),
                'slab_grade': r.get('slab_grade'),
                'weight': r.get('weight', 0),
                'target_thick': r.get('target_thick', 0),
                'target_width': r.get('target_width', 0)
            })
            count += 1

        if batch_update:
            db.save_batch_coils_v2(batch_update)

        return jsonify({'status': 'success', 'msg': f'Đã tính lại điểm cho {count} cuộn {target_grade} (Dữ liệu gốc được bảo toàn)!'})

    except Exception as e:
        print(f"Recalc Error: {e}")
        return jsonify({'status': 'error', 'msg': str(e)})
@dashboard_bp.route('/api/get_input_detail/<coil_id>', methods=['GET'])
def get_input_detail(coil_id):
    try:
        conn = db.get_connection()
        cursor = conn.cursor()
        
        # 1. Lấy dữ liệu từ DB
        cursor.execute("SELECT raw_data, scores, grade, is_checked FROM coil_data WITH (NOLOCK) WHERE coil_id = ?", (coil_id,))
        row = cursor.fetchone()
        conn.close()

        if not row:
            return jsonify({'status': 'error', 'msg': 'Không tìm thấy cuộn'})

        # 2. Parse dữ liệu
        # row[0]: raw_data, row[1]: scores, row[2]: grade
        current_raw = json.loads(row[0]) if row[0] else {}
        current_scores = json.loads(row[1]) if row[1] else {}
        grade = row[2] if row[2] else 'SAE1006'
        
        # 3. TÍNH TOÁN DỮ LIỆU GỐC (REFERENCE) TẠI CHỖ
        # Thay vì lưu vào DB làm nặng, ta tính "tươi" ở đây vì chỉ tính cho 1 cuộn -> Cực nhanh
        all_configs = get_all_grade_configs() # Hàm này đã tối ưu cache ở câu trả lời trước
        auto_scores = process_coil_scores(coil_id, current_raw, grade, cached_config=all_configs)

        return jsonify({
            'status': 'success',
            'data': {
                'coil_id': coil_id,
                'grade': grade,
                'current_scores': current_scores, # Điểm hiện tại (có thể đã sửa)
                'original_scores': auto_scores,   # Điểm gốc máy chấm (tham chiếu)
                'raw_data': current_raw,
                'is_checked': row[3]
            }
        })
    except Exception as e:
        print(f"Err detail: {e}")
        return jsonify({'status': 'error', 'msg': str(e)})
## Nhập tay
@dashboard_bp.route('/get_manual_config', methods=['GET'])
def get_manual_config():
    return jsonify({
        'SURFACE_MANUAL': [{'id': 'oil', 'label': 'Gấp nếp'}, {'id': 'rust', 'label': 'Nếp Nhăn'}, {'id': 'scratch_m', 'label': 'Vết Hằn'}, {'id': 'dirt', 'label': 'Gãy mặt'}, {'id': 'mark', 'label': 'Xỉ thứ cấp'}, {'id': 'scale', 'label': 'Xỉ cán'}, {'id': 'other_s', 'label': 'Xỉ muối tiêu'},{'id': 'gianbien', 'label': 'Giãn biên'}],
        'GEO_MANUAL': [{'id': 'telescope', 'label': 'Cong cạnh'}],
        'APPEARANCE': [{'id': 'strap', 'label': 'Khuyết biên'}, {'id': 'label_tag', 'label': 'Bava biên'}, {'id': 'packaging', 'label': 'Vỡ biên'}, {'id': 'edge_cond', 'label': 'Sổ vòng'}, {'id': 'coil_shape', 'label': 'Loa cuộn'}]
    })
@dashboard_bp.route('/save_manual_data', methods=['POST'])
def save_manual_data():
    conn = None
    try:
        req = request.json
        coil_id = req.get('coil_id')
        new_scores = req.get('scores')
        user_name = req.get('user', 'User')
        new_quality = req.get('quality_level', '')
        is_reset = req.get('is_reset', False)

        if not coil_id: return jsonify({'status':'error', 'msg': 'Thiếu ID cuộn'})

        conn = db.get_connection()
        cursor = conn.cursor() # [FIX 1]: Tạo Cursor
        
        # 1. Lấy dữ liệu cũ để so sánh
        cursor.execute("SELECT scores FROM coil_data WITH (NOLOCK) WHERE coil_id=?", (coil_id,))
        curr_row = cursor.fetchone()
        
        old_scores = json.loads(curr_row[0]) if curr_row and curr_row[0] else {}

        # 2. Ghi Log thay đổi (Audit)
        logs = []
        import datetime
        now = datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")

        for key, new_val in new_scores.items():
            old_val = old_scores.get(key, 0)
            if float(new_val) != float(old_val):
                logs.append((coil_id, user_name, key, float(old_val), float(new_val), now))

        if logs:
            cursor.executemany("INSERT INTO audit_log_qlcl (coil_id, user_name, defect_key, old_value, new_value, changed_at) VALUES (?, ?, ?, ?, ?, ?)", logs)

        # 3. Cập nhật dữ liệu
        final_scores = old_scores.copy()
        final_scores.update(new_scores)
        new_is_checked = 0 if is_reset else 1

        cursor.execute(
            "UPDATE coil_data SET scores = ?, is_checked = ?, quality_level = ? WHERE coil_id = ?", 
            (json.dumps(final_scores), new_is_checked, new_quality, coil_id)
        )
        
        conn.commit() 
        return jsonify({'status': 'success', 'msg': 'Đã lưu thành công!'})

    except Exception as e:
        if conn: conn.rollback() 
        print(f"ERROR save_manual_data: {e}")
        return jsonify({'status':'error', 'msg':str(e)})
    finally:
        if conn: conn.close()
# 1. API KHỞI TẠO BẢNG LOG VÀ CÁC CHỨC NĂNG LIÊN QUAN
@dashboard_bp.route('/api/init_log_table', methods=['GET'])
def init_log_table():
    try:
        conn = db.get_connection()
        # Tạo bảng
        conn.execute("""
            CREATE TABLE IF NOT EXISTS system_logs (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                title TEXT, message TEXT, log_type TEXT,
                is_read INTEGER DEFAULT 0,
                created_at TEXT
            )
        """)
        try: conn.execute("ALTER TABLE system_logs ADD COLUMN is_read INTEGER DEFAULT 0")
        except: pass

        conn.execute("CREATE INDEX IF NOT EXISTS idx_is_read ON system_logs (is_read)")
        
        conn.commit()
        conn.close()
        return jsonify({'status': 'success', 'msg': 'DB Logs Optimized!'})
    except Exception as e:
        return jsonify({'status': 'error', 'msg': str(e)})
@dashboard_bp.route('/api/mark_all_read', methods=['POST'])
def mark_all_read():
    conn = None
    try:
        conn = db.get_connection()
        cursor = conn.cursor() # [SỬA 1]: Tạo cursor
        
        cursor.execute("SELECT TOP 1 1 FROM system_logs WITH (NOLOCK) WHERE is_read = 0")
        check = cursor.fetchone()
        
        if check:
            cursor.execute("UPDATE system_logs SET is_read = 1 WHERE is_read = 0")
            conn.commit()
            
        return jsonify({'status': 'success'})
    except Exception as e:
        print(f"Error mark_all_read: {e}") # In lỗi ra để dễ debug
        return jsonify({'status': 'error', 'msg': str(e)})
    finally:
        if conn: conn.close() # Đảm bảo đóng kết nối
@dashboard_bp.route('/api/get_unread_count', methods=['GET'])
def get_unread_count():
    try:
        conn = db.get_connection()
        cursor = conn.cursor() 
        cursor.execute("SELECT COUNT(*) as cnt FROM system_logs WITH (NOLOCK) WHERE is_read = 0")
        row = cursor.fetchone()
        conn.close()
        return jsonify({'count': row[0]}) 
    except:
        return jsonify({'count': 0})
# 2. API LẤY LỊCH SỬ THÔNG BÁO
@dashboard_bp.route('/api/get_system_logs', methods=['GET'])
def get_system_logs():
    try:
        conn = db.get_connection()
        cursor = conn.cursor()
        cursor.execute("SELECT TOP 50 * FROM system_logs WITH (NOLOCK) ORDER BY id DESC")
        columns = [column[0] for column in cursor.description]
        rows = [dict(zip(columns, row)) for row in cursor.fetchall()]
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
        conn = db.get_connection()
        cursor = conn.cursor()
        cursor.execute("SELECT TOP 1 message, created_at FROM system_logs WITH (NOLOCK) ORDER BY id DESC")
        columns = [column[0] for column in cursor.description]
        last_log_rows = [dict(zip(columns, row)) for row in cursor.fetchall()]

        if last_log_rows:
            last_log = last_log_rows[0]
            if last_log['message'] == message:
                last_time = last_log['created_at']
                if isinstance(last_time, str):
                    try:
                        # Xử lý chuỗi có 'T' hoặc mili-giây
                        clean_t = last_time.replace('T', ' ').split('.')[0]
                        last_time = datetime.datetime.strptime(clean_t, "%Y-%m-%d %H:%M:%S")
                    except: pass
                now_time = datetime.datetime.now()
                if isinstance(last_time, datetime.datetime):
                    diff = (now_time - last_time).total_seconds()
                    if diff < 60: 
                        conn.close()
                        print(f"♻️ [Anti-Spam] Bỏ qua log trùng: {message}")
                        return
        now_str = datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        conn.execute(
            "INSERT INTO system_logs (title, message, log_type, is_read, created_at) VALUES (?, ?, ?, 0, ?)",
            (title, message, log_type, now_str)
        )
        conn.commit()
        conn.close()
    except Exception as e:
        print(f"❌ Lỗi ghi log: {e}")

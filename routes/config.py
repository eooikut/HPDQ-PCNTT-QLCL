from flask import Blueprint, app, render_template, current_app, request, jsonify, session
import threading
import db  # Module db.py
from apscheduler.schedulers.background import BackgroundScheduler
from utils.common import sanitize_data, desanitize_data
from utils.scoring import get_all_grade_configs
import datetime
import json
from auth.decorator import login_required, permission_required
config_bp = Blueprint('config_bp', __name__)
upload_lock = threading.Lock()
@config_bp.route('/config_page', methods=['GET'])
@permission_required('config_manage')
def config_page(): return render_template('config_grade.html')

@config_bp.route('/api/grade_configs', methods=['GET'])
@permission_required('config_manage')
def api_get_configs(): return jsonify(sanitize_data(get_all_grade_configs()))

# API LƯU CẤU HÌNH ĐIỂM SỐ
@config_bp.route('/api/grade_configs', methods=['POST'])
@permission_required('config_manage')
def api_save_configs():
    conn = None
    try:
        new_cfg = desanitize_data(request.json)
        user_name = session.get('username', 'Unknown') # Lấy user thao tác
        
        # 1. Đọc cấu hình cũ từ DB để so sánh (trước khi ghi đè)
        old_cfg = get_all_grade_configs()
        
        # 2. Lưu cấu hình mới
        db.save_config('grade_configs', sanitize_data(new_cfg))
        
        # 3. Phân tích sự thay đổi và Ghi Log vào bảng audit_log_qlcl
        now_str = datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        logs = []
        
        # A. Kiểm tra Mác thép nào bị thêm hoặc sửa
        for grade, config_data in new_cfg.items():
            mapped_id = f"CFG-{grade}" # Thêm tiền tố CFG- để nhận diện là log cấu hình
            
            if grade not in old_cfg:
                # Trường hợp: Thêm mới Mác thép
                logs.append((mapped_id, user_name, 'ADD_GRADE', 0.0, 1.0, now_str))
            else:
                # Trường hợp: Có sửa chữa thông số bên trong Mác thép đó
                # Chuyển dict thành chuỗi string để so sánh xem có khác nhau không
                if json.dumps(old_cfg[grade], sort_keys=True) != json.dumps(config_data, sort_keys=True):
                    logs.append((mapped_id, user_name, 'UPDATE_CONFIG', 1.0, 2.0, now_str))
                    
        # B. Kiểm tra Mác thép nào bị XÓA
        for grade in old_cfg.keys():
            if grade not in new_cfg:
                mapped_id = f"CFG-{grade}"
                logs.append((mapped_id, user_name, 'DELETE_GRADE', 1.0, 0.0, now_str))

        # C. Thực thi Insert xuống DB
        if logs:
            conn = db.get_connection()
            cursor = conn.cursor()
            cursor.executemany("""
                INSERT INTO audit_log_qlcl (coil_id, user_name, defect_key, old_value, new_value, changed_at) 
                VALUES (?, ?, ?, ?, ?, ?)
            """, logs)
            conn.commit()

        return jsonify({'msg': 'Saved'})

    except Exception as e:
        if conn: conn.rollback()
        return jsonify({'msg': str(e)}), 500
    finally:
        if conn: conn.close()
@config_bp.route('/api/get_grade_criteria', methods=['GET'])
@permission_required('config_manage')
def get_grade_criteria():
    """Trả về danh sách các lỗi/chỉ tiêu của một Mác thép để hiện lên Dropdown"""
    try:
        grade = request.args.get('grade', 'SAE1006')
        all_configs = get_all_grade_configs()
        config = all_configs.get(grade, all_configs.get('SAE1006', {}))
        criteria_list = []
        # Các nhóm hiển thị cho đẹp
        group_names = {
            'surface': '1. Bề mặt',
            'geometry': '2. Hình học',
            'mechanical': '3. Cơ lý',
            'chemical': '4. Hóa học'
        }
        for key, cfg in config.items():

            if key in ['heatmap_cols', 'matrix_rules', 'count_limits', 'bins', 'labels']: 
                continue
            # Lấy tên hiển thị (Label)
            label = cfg.get('label', key)
            if cfg.get('target_defect'):
                label = f"{key} ({cfg.get('target_defect')})"

            criteria_list.append({
                'code': key,           
                'name': label,       
                'group': group_names.get(cfg.get('group'), 'Khác')
            })

        # Sắp xếp theo nhóm để hiển thị gọn gàng
        criteria_list.sort(key=lambda x: x['group'])
        
        return jsonify(criteria_list)
    except Exception as e:
        return jsonify([])
from flask import Blueprint, app, render_template, current_app, request, jsonify
import threading
import db  # Module db.py
from apscheduler.schedulers.background import BackgroundScheduler
from utils.common import sanitize_data, desanitize_data
from utils.scoring import get_all_grade_configs
config_bp = Blueprint('config_bp', __name__)
upload_lock = threading.Lock()
@config_bp.route('/config_page', methods=['GET'])
def config_page(): return render_template('config_grade.html')
@config_bp.route('/api/grade_configs', methods=['GET'])
def api_get_configs(): return jsonify(sanitize_data(get_all_grade_configs()))
# API LƯU CẤU HÌNH ĐIỂM SỐ
@config_bp.route('/api/grade_configs', methods=['POST'])
def api_save_configs():
    try:
        new_cfg = desanitize_data(request.json)
        db.save_config('grade_configs', sanitize_data(new_cfg))
        return jsonify({'msg': 'Saved'})
    except Exception as e: return jsonify({'msg': str(e)}), 500
@config_bp.route('/reset_configs', methods=['POST'])
def reset_configs(): 
    conn = db.get_connection()
    conn.execute("DELETE FROM coil_data")
    conn.commit()
    conn.close()
    return jsonify({'status': 'success'})
@config_bp.route('/api/get_grade_criteria', methods=['GET'])
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
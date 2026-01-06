import os
from flask import Flask, redirect, url_for
import db

# 1. Import Scheduler từ file worker mới
from utils.sync_worker import init_scheduler

# 2. Import 5 Blueprint mới
from routes.dashboard import dashboard_bp
from routes.tdc import tdc_bp
from routes.alloc_run import alloc_run_bp
from routes.alloc_hist import alloc_hist_bp
from routes.config import config_bp

app = Flask(__name__)
# Cấu hình dung lượng upload (16MB)
app.config['MAX_CONTENT_LENGTH'] = 16 * 1024 * 1024 

# 3. Đăng ký 5 Blueprint
app.register_blueprint(dashboard_bp)
app.register_blueprint(tdc_bp)
app.register_blueprint(alloc_run_bp)
app.register_blueprint(alloc_hist_bp)
app.register_blueprint(config_bp)

# Route mặc định: Chuyển hướng về Dashboard
@app.route('/')
def index():
    return redirect(url_for('dashboard_bp.qlcl_page')) 
    # Lưu ý: Trong dashboard.py bạn đặt tên blueprint là 'qlcl_bp' hay 'dashboard_bp'?
    # Nếu trong dashboard.py bạn để: dashboard_bp = Blueprint('dashboard', __name__)
    # Thì sửa dòng trên thành: return redirect(url_for('dashboard.qlcl_page'))

if __name__ == '__main__':
    # Khởi tạo Database Audit Log
    try:
        db.init_audit_log_qlcl()
    except Exception as e:
        print("⚠️ Cảnh báo Log:", e)

    # Khởi chạy Scheduler (Chỉ chạy 1 lần ở process chính)
    if not app.debug or os.environ.get('WERKZEUG_RUN_MAIN') == 'true':
        try:
            print("⏳ Đang khởi động Scheduler...")
            init_scheduler()
        except Exception as e:
            print(f"❌ Lỗi khởi động Scheduler: {e}")

    # Chạy App
    app.run(host="0.0.0.0", port=5001, debug=True)
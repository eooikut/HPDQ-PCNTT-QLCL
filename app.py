import os

import logging

from flask import Flask, redirect, url_for

from flask_compress import Compress

from cheroot.wsgi import Server

from cheroot.ssl.builtin import BuiltinSSLAdapter



# --- 1. Import các module nội bộ của bạn ---

# (Đảm bảo các file này tồn tại trong thư mục project)

import db

from utils.sync_worker import init_scheduler

from flask_wtf.csrf import CSRFProtect

# --- 2. Import 5 Blueprint mới ---

from routes.dashboard import dashboard_bp

from routes.tdc import tdc_bp

from routes.alloc_run import alloc_run_bp

from routes.alloc_hist import alloc_hist_bp

from routes.config import config_bp

from routes.cpk import cpk_bp

from routes.yccn import yccn_bp

from auth.routes import auth_bp

from routes.order_rules_bp import order_rules_bp    

from routes.heatmap_api import heatmap_bp
from routes.qc_dashboard import qc_dash_bp
# from auth.routes import auth_bp
# --- Cấu hình Logging ---

logging.basicConfig(level=logging.INFO)

logger = logging.getLogger("App_8086")
app = Flask(__name__)

# --- Cấu hình App ---

# Cấu hình dung lượng upload (16MB)
app.secret_key = 'mot_chuoi_bao_mat_bat_ky_nen_de_trong_env' # BẮT BUỘC để dùng session
csrf = CSRFProtect(app) # Kích hoạt CSRF cho form login 

app.config['MAX_CONTENT_LENGTH'] = 16 * 1024 * 1024 

app.config['COMPRESS_ALGORITHM'] = 'gzip'

app.config['COMPRESS_LEVEL'] = 6

app.config['COMPRESS_MIN_SIZE'] = 500 



# Kích hoạt nén

Compress(app)



# --- 3. Đăng ký 5 Blueprint ---

app.register_blueprint(dashboard_bp)

app.register_blueprint(tdc_bp)

app.register_blueprint(alloc_run_bp)

app.register_blueprint(alloc_hist_bp)

app.register_blueprint(config_bp)

app.register_blueprint(cpk_bp)

app.register_blueprint(yccn_bp)
app.register_blueprint(order_rules_bp)
app.register_blueprint(heatmap_bp)
app.register_blueprint(qc_dash_bp)
 # Đăng ký Blueprint heatmap_bp
 # Đăng ký Blueprint order_rules_bp
# --- Route mặc định ---
csrf.exempt(dashboard_bp)
csrf.exempt(tdc_bp)
csrf.exempt(alloc_run_bp)
csrf.exempt(alloc_hist_bp)
csrf.exempt(config_bp)
csrf.exempt(cpk_bp)
csrf.exempt(yccn_bp)
csrf.exempt(order_rules_bp)
csrf.exempt(heatmap_bp) 
csrf.exempt(qc_dash_bp)
# Miễn CSRF cho heatmap_bp vì nó chỉ trả về JSON, không có form
app.register_blueprint(auth_bp) 
 # Đăng ký Blueprint auth sau cùng để ưu tiên các route khác
@app.route('/')

def index():

    return redirect(url_for('auth.login'))  # Chuyển hướng đến trang login

if __name__ == "__main__":
    try:
        init_scheduler()
    except Exception as e:
        logger.error(f"❌ Lỗi: {e}")
    # Chạy trên cổng 8087
    app.run(host="0.0.0.0", port=5005, debug=True)
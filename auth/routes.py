from flask import Blueprint, render_template, request, redirect, url_for, flash, session
from werkzeug.security import check_password_hash
from db import get_db_engine
from sqlalchemy import text

auth_bp = Blueprint('auth', __name__, template_folder='../templates') # Điều chỉnh template_folder nếu cần

@auth_bp.route('/login', methods=['GET', 'POST'])
def login():
    # Nếu đã đăng nhập rồi thì không cho vào trang login nữa, đẩy thẳng vào app
    if 'user_id' in session:
        return redirect_based_on_role()

    if request.method == 'POST':
        username = request.form.get('username', '').strip()
        password = request.form.get('password', '').strip()

        if not username or not password:
            flash('Vui lòng nhập đầy đủ tên đăng nhập và mật khẩu', 'danger')
            return redirect(url_for('auth.login'))
            
        engine = get_db_engine()
        with engine.begin() as conn:
            # Truy vấn thông tin user
            query = text("SELECT id, username, password_hash, role, status FROM users WHERE username = :username")
            result = conn.execute(query, {"username": username}).mappings().fetchone()

            if result and check_password_hash(result['password_hash'], password):
                # Kiểm tra tài khoản có bị vô hiệu hóa không
                if result.get('status') != 1:
                    flash('Tài khoản của bạn đã bị vô hiệu hóa. Vui lòng liên hệ quản trị viên.', 'danger')
                    return redirect(url_for('auth.login'))
    
                # Lưu thông tin cơ bản vào session
                session['user_id'] = result['id']
                session['username'] = result['username']
                session['role'] = result['role'].strip().lower()
    
                # Lấy danh sách quyền của user (nếu không phải admin)
                if session['role'] != 'admin':
                    perm_query = text("SELECT permission_name FROM user_permissions WHERE user_id = :uid")
                    permissions_result = conn.execute(perm_query, {"uid": result['id']}).fetchall()
                    session['permissions'] = [p[0] for p in permissions_result]
                else:
                    session['permissions'] = ['all'] # Admin có toàn quyền
    
                # Cập nhật thời gian đăng nhập lần cuối
                update_query = text("UPDATE users SET last_login = GETDATE() WHERE id = :id")
                conn.execute(update_query, {"id": result['id']})
    
                flash('Đăng nhập thành công', 'success')
                return redirect_based_on_role()

        # Nếu sai username hoặc password
        flash('Sai tên đăng nhập hoặc mật khẩu', 'danger')
        return redirect(url_for('auth.login'))

    return render_template('login.html')

@auth_bp.route('/logout')
def logout():
    session.clear() # Xóa sạch toàn bộ session
    flash('Đã đăng xuất', 'success')
    return redirect(url_for('auth.login'))

# --- HÀM HỖ TRỢ CHUYỂN HƯỚNG ---
def redirect_based_on_role():
    """Hàm xử lý logic chuyển hướng thông minh sau khi đăng nhập"""
    role = session.get('role')
    perms = session.get('permissions', [])

    # 1. Admin luôn được đưa về trang Dashboard tổng quan nhất
    if role == 'admin' or 'all' in perms:
        return redirect(url_for('dashboard_bp.qlcl_page'))

    # 2. Map quyền với TÊN BLUEPRINT.TÊN HÀM (Cực kỳ quan trọng, phải chuẩn xác 100%)
    # Thứ tự từ trên xuống dưới là ĐỘ ƯU TIÊN chuyển hướng khi user có nhiều quyền
    # KEY (bên trái) là tên quyền TRONG DATABASE của bạn
    # VALUE (bên phải) là route endpoint tương ứng
    permission_routes = {
        'qlcl_view': 'dashboard_bp.qlcl_page',               # Ưu tiên 1: Trang QLCL
        'allocation_run': 'alloc_run_bp.allocation_run_page', # Ưu tiên 2: Chạy phân bổ
        'allocation_history': 'alloc_hist_bp.allocation_history_page', 
        'cpk_view': 'cpk_bp.cpk_page',
        'tdc_view': 'tdc_bp.tdc_manager_page',               # Thư viện TDC
        'tdc_editor': 'tdc_bp.tdc_manager_page',             # Tạo TDC (Cùng vào trang Manager)
        'tdc_approval': 'tdc_bp.tdc_manager_page',           # Phê duyệt TDC (Cùng vào trang Manager)
        'complaint_view': 'tdc_bp.tdc_dashboard_page',       # Khiếu nại Dashboard
        'yccn_manage': 'yccn_bp.yccn_manager_page',
        'config_manage': 'config_bp.config_page'
    }

    # Quét xem user có quyền nào đầu tiên trong danh sách ưu tiên thì đẩy vào trang đó
    for perm, route in permission_routes.items():
        if perm in perms:
            return redirect(url_for(route))

    # 3. Nếu không có bất kỳ quyền nào được map ở trên (hoặc user chưa được cấp quyền giao diện)
    return render_template('403.html') # Giao diện báo lỗi "Không có quyền truy cập"
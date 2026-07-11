from functools import wraps
from flask import session, redirect, url_for, flash, request, jsonify, render_template

def login_required(f):
    """
    Đảm bảo người dùng đã đăng nhập.
    """
    @wraps(f)
    def decorated_function(*args, **kwargs):
        if 'user_id' not in session:
            flash("Bạn cần đăng nhập để truy cập trang này.", "warning")
            return redirect(url_for('auth.login'))
        return f(*args, **kwargs)
    return decorated_function

def admin_required(f):
    """
    Đảm bảo người dùng là admin.
    """
    @wraps(f)
    @login_required
    def decorated_function(*args, **kwargs):
        if session.get('role') != 'admin':
            flash("Bạn không có quyền truy cập chức năng này.", "danger")
            return redirect(url_for('tau_bp.lichtau')) # Hoặc trang chủ
        return f(*args, **kwargs)
    return decorated_function

def permission_required(*permissions):
    """
    Đảm bảo người dùng có ÍT NHẤT 1 quyền trong danh sách yêu cầu HOẶC là admin
    """
    def decorator(f):
        @wraps(f)
        @login_required
        def decorated_function(*args, **kwargs):
            role = session.get('role', '')
            perms = session.get('permissions', [])
            
            # ĐIỀU KIỆN VÀNG (Nâng cấp): 
            # Nếu là admin HOẶC có quyền 'all' HOẶC có ít nhất 1 quyền khớp với yêu cầu
            if role == 'admin' or 'all' in perms or any(p in perms for p in permissions):
                return f(*args, **kwargs)
                
            # XỬ LÝ KHI BỊ CHẶN (Giữ nguyên 100% logic của bạn):
            # 1. Nếu Frontend đang gọi API ngầm lấy dữ liệu -> Trả về lỗi JSON
            if request.path.startswith('/api/') or request.path.startswith('/save_') or request.path.startswith('/get_'):
                return jsonify({'status': 'error', 'msg': 'Bạn không có thẩm quyền (Forbidden)!'}), 403
                
            # 2. Nếu Frontend đang load một trang web -> Đẩy về trang báo lỗi
            flash("Bạn không có quyền truy cập chức năng này.", "danger")
            return render_template('403.html') 
            
        return decorated_function
    return decorator
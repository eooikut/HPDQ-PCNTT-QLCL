from flask import Blueprint, request, jsonify, current_app
import db
import json
import os
from werkzeug.utils import secure_filename
import time
import datetime

yccn_bp = Blueprint('yccn_bp', __name__)

# Config folder upload riêng cho YCCN
UPLOAD_FOLDER = 'static/uploads/yccn_pdfs'
os.makedirs(UPLOAD_FOLDER, exist_ok=True)

# 1. Route render giao diện
@yccn_bp.route('/yccn_manager', methods=['GET'])
def yccn_manager_page():
    return current_app.jinja_env.get_template('yccn_manager.html').render()

# 2. API Upload PDF
@yccn_bp.route('/api/yccn/upload', methods=['POST'])
def upload_yccn_pdf():
    if 'file' not in request.files: return jsonify({'status':'error', 'msg':'No file'})
    f = request.files['file']
    if f.filename == '': return jsonify({'status':'error', 'msg':'No filename'})
    
    if f:
        # 1. Lưu file
        filename = secure_filename(f"yccn_{int(time.time())}_{f.filename}")
        sys_path = os.path.join(UPLOAD_FOLDER, filename)
        f.save(sys_path)
        
        # 2. Tạo đường dẫn web
        web_path = f"/{sys_path}".replace("\\", "/")
        
        return jsonify({'status':'success', 'path': web_path})
@yccn_bp.route('/api/yccn/upload_multi', methods=['POST'])
def upload_multi_yccn_pdf():
    # Sử dụng getlist để lấy toàn bộ file từ form (tên key là 'files')
    files = request.files.getlist('files')
    if not files or len(files) == 0: 
        return jsonify({'status':'error', 'msg':'Không có file nào được chọn'})
    
    paths = []
    for f in files:
        if f and f.filename != '':
            # Lưu từng file
            filename = secure_filename(f"yccn_{int(time.time())}_{f.filename}")
            sys_path = os.path.join(UPLOAD_FOLDER, filename)
            f.save(sys_path)
            
            # Tạo đường dẫn web và thêm vào mảng
            web_path = f"/{sys_path}".replace("\\", "/")
            paths.append(web_path)
            
    return jsonify({'status':'success', 'paths': paths})
# 3. API Lưu YCCN (Xử lý Smart Mapping từ Frontend)
@yccn_bp.route('/api/yccn/save_direct', methods=['POST'])
def save_yccn_direct():
    req = request.json
    conn = None
    try:
        conn = db.get_connection()
        cursor = conn.cursor()
        
        # Lấy dữ liệu
        master_id = req.get('master_id') # Nếu rỗng -> Thêm mới, Nếu có -> Cập nhật version
        
        code = req.get('yccn_code')
        title = req.get('title')
        factory = req.get('factory')
        cate = req.get('category')
        
        # Các trường phân cấp (Đã được Frontend Smart Mapping)
        process = req.get('process')
        grade = req.get('grade_apply')
        slab = req.get('slab_grade')
        usage = req.get('usage_purpose')
        
        if not code or not title or not factory:
             return jsonify({'status': 'error', 'msg': 'Thiếu thông tin: Mã, Tên hoặc Nhà máy!'})

        # === LOGIC XỬ LÝ MASTER ===
        
        # TRƯỜNG HỢP 1: THÊM MỚI TÀI LIỆU
        if not master_id:
            # Kiểm tra xem Mã này đã tồn tại chưa?
            cursor.execute("SELECT id FROM yccn_master WHERE yccn_code = ?", (code,))
            existing_code = cursor.fetchone() 
            existing_phase = None
            if cate == 'NPD':
                cursor.execute("SELECT id FROM yccn_master WHERE title = ? AND usage_purpose = ?", (title, usage))
                existing_phase = cursor.fetchone()

            # Rào chắn báo lỗi
            if existing_code or existing_phase:
                if cate == 'NPD' and existing_phase:
                    error_msg = f'LỖI: Giai đoạn "{usage}" của Dự án "{title}" đã tồn tại! Vui lòng chọn tài liệu trên cây thư mục và nhấn [Cập nhật v2].'
                else:
                    error_msg = f'LỖI: Mã tài liệu "{code}" đã tồn tại! Vui lòng kiểm tra lại.'
                
                return jsonify({'status': 'error', 'msg': error_msg})
            
            # Nếu chưa có -> Insert Master mới
            cursor.execute("""
                SET NOCOUNT ON;
                INSERT INTO yccn_master 
                (yccn_code, category, title, factory_code, process_stage, usage_purpose, created_at)
                VALUES (?, ?, ?, ?, ?, ?, GETDATE());
                SELECT SCOPE_IDENTITY();
            """, (code, cate, title, factory, process, usage))
            
            res = cursor.fetchone()
            if res:
                master_id = res[0]
            else:
                # Fallback an toàn nếu SCOPE_IDENTITY bị miss
                cursor.execute("SELECT id FROM yccn_master WHERE yccn_code = ?", (code,))
                master_id = cursor.fetchone()[0]

        # TRƯỜNG HỢP 2: CẬP NHẬT (Gia hạn version mới)
        else:
            # Cập nhật lại thông tin Master lỡ người dùng có sửa Tên/Mác thép...
            cursor.execute("""
                UPDATE yccn_master 
                SET title=?, category=?, factory_code=?, process_stage=?, usage_purpose=?
                WHERE id=?
            """, (title, cate, factory, process, usage, master_id))
            
            # Lưu ý: Không cho phép UPDATE yccn_code ở đây để đảm bảo tính toàn vẹn dữ liệu

        # === LOGIC XỬ LÝ VERSION MỚI ===
        
        # 1. Tính số version tiếp theo
        cursor.execute("SELECT ISNULL(MAX(version_no), 0) + 1 FROM yccn_versions WHERE master_id = ?", (master_id,))
        next_ver = cursor.fetchone()[0]

        # 2. Vô hiệu hóa bản cũ (Chuyển Active -> Replaced)
        cursor.execute("UPDATE yccn_versions SET status = 'Replaced' WHERE master_id = ? AND status = 'Active'", (master_id,))

        # 3. Insert bản mới và Kích hoạt ngay (Active)
        cursor.execute("""
            INSERT INTO yccn_versions 
            (master_id, version_no, grade_apply, slab_grade, pdf_path, valid_from, valid_to, status, created_at, note)
            VALUES (?, ?, ?, ?, ?, ?, ?, 'Active', GETDATE(), ?)
        """, (
            master_id, 
            next_ver, 
            grade, 
            slab, 
            req.get('pdf_path',''), 
            req.get('valid_from'), 
            req.get('valid_to'), 
            req.get('note','')
        ))
        
        conn.commit()
        return jsonify({'status': 'success', 'msg': f'Đã lưu và kích hoạt thành công phiên bản v{next_ver}!'})

    except Exception as e:
        if conn: conn.rollback()
        print("Lỗi Save Direct YCCN:", e)
        return jsonify({'status': 'error', 'msg': f'Lỗi DB: {str(e)}'})
    finally:
        if conn: conn.close()

# 4. API Lấy danh sách toàn bộ Thư viện (Chỉ lấy bản Active)
@yccn_bp.route('/api/yccn/library', methods=['GET'])
def get_yccn_library():
    # Gọi hàm đã có sẵn trong db.py
    data = db.get_active_yccn_list() 
    return jsonify(data)

# 5. API Lấy lịch sử các phiên bản của 1 tài liệu
@yccn_bp.route('/api/yccn/history', methods=['POST'])
def get_yccn_history():
    req = request.json
    master_id = req.get('master_id')
    if not master_id: 
        return jsonify({'status':'error', 'msg':'Thiếu Master ID'})
    
    data = db.get_yccn_history(master_id)
    return jsonify({'status':'success', 'data': data})
@yccn_bp.route('/api/yccn/update_master_info', methods=['POST'])
def update_master_info():
    req = request.json
    master_id = req.get('master_id')
    new_title = req.get('title')
    new_usage = req.get('usage_purpose')

    if not master_id or not new_title:
        return jsonify({'status': 'error', 'msg': 'Thiếu ID hoặc Tiêu đề'})

    conn = db.get_connection()
    try:
        cursor = conn.cursor()
        cursor.execute("""
            UPDATE yccn_master 
            SET title = ?, usage_purpose = ? 
            WHERE id = ?
        """, (new_title, new_usage, master_id))
        conn.commit()
        return jsonify({'status': 'success', 'msg': 'Đã cập nhật lại thông tin gốc!'})
    except Exception as e:
        if conn: conn.rollback()
        return jsonify({'status': 'error', 'msg': str(e)})
    finally:
        if conn: conn.close()
# Tương lai nếu bạn cần thêm API Xóa/Vô hiệu hóa tài liệu có thể viết tiếp ở đây...
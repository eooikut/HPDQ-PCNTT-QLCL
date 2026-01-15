from flask import Blueprint, request, jsonify, current_app
import db
import json
import os
from werkzeug.utils import secure_filename
import time
import re
tdc_bp = Blueprint('tdc_bp', __name__)

# Config folder upload
UPLOAD_FOLDER = 'static/uploads/pdfs'
os.makedirs(UPLOAD_FOLDER, exist_ok=True)

@tdc_bp.route('/tdc_manager', methods=['GET'])
def tdc_manager_page():
    # Render file html mới
    return current_app.jinja_env.get_template('tdc_manager.html').render()

# API 1: Lấy danh sách thư viện TDC (Chỉ Active)
@tdc_bp.route('/api/get_tdc_library', methods=['GET'])
def get_tdc_library():
    # Sử dụng hàm mới lấy list Active
    data = db.get_active_tdc_list()
    for d in data:
        if d['criteria_json']: d['criteria'] = json.loads(d['criteria_json'])
    return jsonify(data)

# [MỚI] API 1b: Lấy danh sách Pending (Chờ duyệt)
@tdc_bp.route('/api/get_tdc_pending', methods=['GET'])
def get_tdc_pending():
    data = db.get_tdc_pending_list()
    for d in data:
        if d['criteria_json']: d['criteria'] = json.loads(d['criteria_json'])
    return jsonify(data)

# [MỚI] API 1c: Lấy lịch sử Version
@tdc_bp.route('/api/get_tdc_history', methods=['POST'])
def get_tdc_history():
    req = request.json
    master_id = req.get('master_id')
    if not master_id: return jsonify({'status':'error', 'msg':'Thiếu Master ID'})
    
    data = db.get_tdc_history(master_id)
    for d in data:
        if d['criteria_json']: d['criteria'] = json.loads(d['criteria_json'])
    return jsonify({'status':'success', 'data': data})

# API 2: Upload PDF
@tdc_bp.route('/api/upload_tdc_pdf', methods=['POST'])
def upload_tdc_pdf():
    if 'file' not in request.files: return jsonify({'status':'error', 'msg':'No file'})
    f = request.files['file']
    if f.filename == '': return jsonify({'status':'error', 'msg':'No filename'})
    
    if f:
        filename = secure_filename(f"{int(time.time())}_{f.filename}")
        path = os.path.join(UPLOAD_FOLDER, filename)
        f.save(path)
        return jsonify({'status':'success', 'path': f"/{path}"}) # Trả về đường dẫn web

# API 3: Lưu TDC Version (Draft / Pending)
@tdc_bp.route('/api/save_tdc_master', methods=['POST'])
def save_tdc_master_endpoint():
    req = request.json
    conn = db.get_connection()
    cursor = conn.cursor()
    
    try:
        # Dữ liệu từ form
        code = req.get('tdc_code')
        cust = req.get('customer_name')
        purpose = req.get('usage_purpose')
        grade = req.get('grade')
        
        # --- BƯỚC 1 & 2: XỬ LÝ MASTER (Tìm hoặc Tạo) ---
        cursor.execute("SELECT id FROM tdc_master WHERE tdc_code = ?", (code,))
        row = cursor.fetchone()
        
        if row:
            # Đã tồn tại -> Dùng lại ID cũ (Truy cập bằng index 0)
            master_id = row[0] 
            
            # (Tùy chọn) Cập nhật lại thông tin Master
            cursor.execute("""
                UPDATE tdc_master 
                SET customer_name = ?, usage_purpose = ?, grade = ? 
                WHERE id = ?
            """, (cust, purpose, grade, master_id))
        else:
            # Chưa có -> Tạo mới
            cursor.execute("""
                INSERT INTO tdc_master (tdc_code, customer_name, usage_purpose, grade, created_at)
                VALUES (?, ?, ?, ?, GETDATE())
            """, (code, cust, purpose, grade))
            
            # Lấy ID vừa tạo
            cursor.execute("SELECT SCOPE_IDENTITY()")
            master_id = cursor.fetchone()[0] # <--- SỬA LỖI: Dùng index 0

        # --- BƯỚC 3: TÍNH VERSION TIẾP THEO ---
        cursor.execute("SELECT ISNULL(MAX(version_no), 0) + 1 FROM tdc_versions WHERE master_id = ?", (master_id,))
        next_ver = cursor.fetchone()[0] # <--- SỬA LỖI: Dùng index 0

        # --- BƯỚC 4: TẠO VERSION MỚI (Pending) ---
        cursor.execute("""
            INSERT INTO tdc_versions 
            (master_id, version_no, criteria_json, pdf_path, valid_from, valid_to, status, created_at)
            VALUES (?, ?, ?, ?, ?, ?, 'Pending', GETDATE())
        """, (
            master_id, 
            next_ver, 
            json.dumps(req.get('criteria', [])), 
            req.get('pdf_path', ''),
            req.get('valid_from'), 
            req.get('valid_to')
        ))
        
        conn.commit()
        return jsonify({'status': 'success', 'msg': f'Đã lưu phiên bản v{next_ver} (Chờ duyệt)'})

    except Exception as e:
        if conn: conn.rollback()
        print("Lỗi Save TDC:", str(e))
        return jsonify({'status': 'error', 'msg': str(e)})
    finally:
        if conn: conn.close()

# [MỚI] API: Phê duyệt Version
@tdc_bp.route('/api/confirm_tdc', methods=['POST'])
def confirm_tdc_endpoint():
    req = request.json
    # Tiếp nhận đầy đủ các trường dữ liệu được chỉnh sửa từ Tab Approval
    data = {
        'version_id': req.get('version_id'),
        'cust': req.get('customer_name'),
        'grade': req.get('grade'),
        'purpose': req.get('usage_purpose'),
        'valid_from': req.get('valid_from'),
        'valid_to': req.get('valid_to'),
        'criteria': req.get('criteria', [])
    }
    
    if not data['version_id']: 
        return jsonify({'status':'error', 'msg':'Missing Version ID'})
    try:
        conn = db.get_connection()
        cursor = conn.cursor()
        cursor.execute("SELECT master_id FROM tdc_versions WHERE id = ?", (data['version_id'],))
        master_id = cursor.fetchone()[0]
        conn.close()

        is_overlap, err = db.check_tdc_overlap(master_id, data['valid_from'], data['valid_to'], exclude_version_id=data['version_id'])
        if is_overlap:
            return jsonify({'status': 'error', 'msg': f"Duyệt thất bại: {err}"})
    except Exception as e:
        return jsonify({'status': 'error', 'msg': f"Lỗi kiểm tra trùng lặp: {str(e)}"})
    success, msg = db.confirm_tdc_version(data) 
    if success:
        return jsonify({'status':'success', 'msg': msg})
    else:
        return jsonify({'status':'error', 'msg': msg})

# API: Thay đổi trạng thái sang Rejected
@tdc_bp.route('/api/reject_tdc', methods=['POST'])
def reject_tdc_endpoint():
    req = request.json
    ver_id = req.get('version_id')
    reason = req.get('reason', '')
    if not ver_id: return jsonify({'status':'error', 'msg':'Missing Version ID'})
    
    success, msg = db.reject_tdc_version(ver_id, reason)
    if success:
        return jsonify({'status':'success', 'msg': msg})
    else:
        return jsonify({'status':'error', 'msg': msg})

# API 4: Xóa TDC
@tdc_bp.route('/api/delete_tdc', methods=['POST'])
def delete_tdc_endpoint():
    req = request.json
    if db.delete_tdc(req.get('id')):
        return jsonify({'status':'success'})
    else:
        return jsonify({'status':'error', 'msg':'Không thể xóa (Đang được sử dụng hoặc lỗi DB)'})
@tdc_bp.route('/api/sap/get_customers', methods=['GET'])
def get_sap_customers():
    try:
        conn = db.get_connection()
        # Lấy danh sách khách hàng duy nhất từ bảng SO
        query = "SELECT DISTINCT [Customer] FROM [factory].[dbo].[so] WITH (NOLOCK) ORDER BY [Customer]"
        cursor = conn.cursor()
        cursor.execute(query)
        rows = cursor.fetchall() # Trả về list of tuples
        conn.close() 
        
        # Chuyển về list string đơn giản
        customers = [row[0] for row in rows if row[0]]
        return jsonify({'status': 'success', 'data': customers})
    except Exception as e:
        return jsonify({'status': 'error', 'msg': str(e)})

# --- [MỚI] API 6: Lấy Mác thép theo Khách hàng từ SAP ---
@tdc_bp.route('/api/sap/get_grades_by_cust', methods=['POST'])
def get_grades_by_cust():
    try:
        req = request.json
        cust_name = req.get('customer_name')
        if not cust_name: return jsonify({'status':'error', 'msg':'Thiếu tên khách hàng'})

        conn = db.get_connection()
        # Lấy Description của khách hàng này để parse Mác thép
        query = "SELECT DISTINCT [Item Description] FROM [factory].[dbo].[so] WITH (NOLOCK) WHERE [Customer] = ?"
        cursor = conn.cursor()
        cursor.execute(query, (cust_name,))
        rows = cursor.fetchall()
        conn.close()

        # Logic Parse Mác thép (Giống bên Allocation)
        grades = set()
        for r in rows:
            desc = r[0] # VD: Thép HRC HSPM 2.00x1250 SPHC
            if not desc: continue
            
            # Regex tìm kích thước (VD: 2.00x1250)
            dim_match = re.search(r'(\d+(?:\.\d+)?)\s*[xX]\s*(\d+(?:\.\d+)?)', desc)
            if dim_match:
                # Lấy phần chuỗi SAU kích thước
                remaining = desc[dim_match.end():].strip()
                if remaining:
                    # Mác thép thường là từ đầu tiên sau kích thước
                    parts = remaining.split()
                    raw_grade = parts[0].strip().upper()
                    # Loại bỏ các từ rác nếu cần (VD: COIL, PICKLED...)
                    if len(raw_grade) > 2: # Mác thép ít nhất 3 ký tự
                        grades.add(raw_grade)

        return jsonify({'status': 'success', 'data': sorted(list(grades))})
    except Exception as e:
        return jsonify({'status': 'error', 'msg': str(e)})
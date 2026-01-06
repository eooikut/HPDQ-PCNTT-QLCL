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

# API 1: Lấy danh sách thư viện TDC
@tdc_bp.route('/api/get_tdc_library', methods=['GET'])
def get_tdc_library():
    data = db.get_tdc_master_list()
    # Parse JSON criteria để frontend dùng
    for d in data:
        if d['criteria_json']: d['criteria'] = json.loads(d['criteria_json'])
    return jsonify(data)

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

# API 3: Lưu Master TDC (Bỏ quy cách)
@tdc_bp.route('/api/save_tdc_master', methods=['POST'])
def save_tdc_master_endpoint():
    req = request.json
    # Map dữ liệu từ frontend vào DB
    data = {
        'id': req.get('id'),
        'code': req.get('tdc_code'),
        'cust': req.get('customer_name'),
        'purpose': req.get('usage_purpose'),
        'grade': req.get('grade'),
        'criteria': req.get('criteria', []),
        'pdf': req.get('pdf_path', '')
    }
    
    if not data['cust'] or not data['purpose']:
        return jsonify({'status':'error', 'msg':'Thiếu tên khách hoặc mục đích!'})

    if db.save_tdc_master(data):
        return jsonify({'status':'success', 'msg':'Đã lưu Tiêu chuẩn kỹ thuật!'})
    else:
        return jsonify({'status':'error', 'msg':'Lỗi DB'})

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
from flask import Blueprint, render_template, request, jsonify
import json
from datetime import datetime, timedelta
import db # Kế thừa module db.py hiện tại của bạn
import re
heatmap_bp = Blueprint('heatmap_bp', __name__)

# Đặt ngày mốc (Anchor Date) cho Kíp A làm Ca 1. Hãy sửa lại ngày này theo thực tế xưởng của bạn.
# ANCHOR_DATE = datetime(2026, 1, 12).date()
# CREW_CYCLE = ['A', 'B', 'C']

# def get_logic_shift(prod_date):
#     """Nội suy Ca (1/2) và Kíp (A/B/C) từ thời gian sản xuất khi SAP trễ"""
#     if not prod_date: return 'Unknown'
#     if isinstance(prod_date, str):
#         try:
#             prod_date = datetime.strptime(prod_date.split('.')[0].replace('T', ' '), "%Y-%m-%d %H:%M:%S")
#         except Exception:
#             return 'Unknown'

#     hour = prod_date.hour
#     if 8 <= hour < 20:
#         shift_num = 1
#         logic_date = prod_date.date()
#     else:
#         shift_num = 2
#         if hour < 8:
#             logic_date = (prod_date - timedelta(days=1)).date()
#         else:
#             logic_date = prod_date.date()

#     days_diff = (logic_date - ANCHOR_DATE).days
#     total_shifts_passed = (days_diff * 2) + (shift_num - 1)
#     crew = CREW_CYCLE[total_shifts_passed % 3]

#     return f"{shift_num}{crew}"

# Nhóm các chỉ tiêu để tính toán
DEFECT_GROUPS = {
    'SURFACE': ['MI', 'HPrScale', 'EL', 'HOLE', 'RIP', 'BRUS', 'LC', 'SCRT','XC', 'XTC','TCPK-n', 'oil', 'rust', 'scratch_m', 'dirt',  'other_s', 'gianbien','chambi'],
    'GEOMETRY': ['Crown', 'Wedge', 'ThickDiff', 'WidthDiff', 'telescope' , 'high_spot', 'dungsaitrong'],
    'PROP': ['YieldPoint', 'Tensile', 'Elongation', 'Hardness', 'C', 'Mn', 'Si', 'P', 'S', 'Cu', 'Ni', 'Cr', 'Mo', 'V', 'Ti', 'Al', 'Ca', 'B', 'Nb', 'CEV', 'O', 'N', 'H'],
    'APP': ['strap', 'label_tag', 'packaging', 'edge_cond', 'coil_shape', 'mop_bien']
}

@heatmap_bp.route('/heatmap_dashboard')
def heatmap_page():
    return render_template('heatmap_dashboard.html')

@heatmap_bp.route('/api/get_heatmap_matrix', methods=['POST'])
def get_heatmap_matrix():
    try:
        # 1. NHẬN DỮ LIỆU TỪ FRONTEND
        req = request.json
        factory = req.get('factory', 'HRC1')
        start_date = req.get('start_date')
        end_date = req.get('end_date')
        shift_filter = req.get('shift', 'ALL')
        coil_ids_raw = req.get('coil_ids', '')
        po_ids_raw = req.get('po_ids', '')
        so_mapping = req.get('so_mapping', '').strip()
        # 2. XÂY DỰNG QUERY TRUY VẤN SQL LINH HOẠT
        conn = db.get_connection()
        cursor = conn.cursor()
        
        sql = "SELECT coil_id, weight, production_date, Ca, scores, [Order], prime_status, qc_status FROM coil_data WITH (NOLOCK) WHERE 1=1"
        params = []
        if coil_ids_raw:
            ids = [x.strip().upper() for x in re.split(r'[\s,;]+', coil_ids_raw) if x.strip()]
            if ids:
                placeholders = ','.join(['?'] * len(ids))
                sql += f" AND coil_id IN ({placeholders})"
                params.extend(ids)
                
        # ƯU TIÊN 2: PO / ORDER (Chỉ chạy nếu không có ID Cuộn)
        elif po_ids_raw:
            pos = [x.strip() for x in re.split(r'[\s,;]+', po_ids_raw) if x.strip()]
            if pos:
                placeholders = ','.join(['?'] * len(pos))
                sql += f" AND [Order] IN ({placeholders})" 
                params.extend(pos)
                
        # ƯU TIÊN 3: SO MAPPING (Chỉ chạy nếu không có ID Cuộn và PO)
        elif so_mapping:
            sql += """ AND [Order] IN (
                SELECT [Order] FROM order_production_rules WITH (NOLOCK) 
                WHERE SO_mapping = ?
            )"""
            params.append(so_mapping)
            
        # ƯU TIÊN 4: LỌC NGÀY & NHÀ MÁY (Mặc định)
        else:
            sql += " AND factory = ?"
            params.append(factory)
            if start_date:
                sql += " AND production_date >= ?"
                params.append(f"{start_date} 00:00:00")
            if end_date:
                sql += " AND production_date <= ?"
                params.append(f"{end_date} 23:59:59.999")

        cursor.execute(sql, tuple(params))
        rows = db.fetchall_as_dict(cursor)
        conn.close()

        # 3. KHỞI TẠO BIẾN THỐNG KÊ (KPIs) VÀ MA TRẬN 
        kpis = {
            'total_coils': 0, 'total_weight': 0.0, 'missing_weight': 0, 'missing_mech': 0,
            'w_prime_pass': 0.0,
            'w_nonprime_pass': 0.0,
            'w_scrap_pass': 0.0,
            'w_surf_pass_nochem': 0.0,
            'w_unassigned_pending': 0.0,
            'w_processing': 0.0
        }
        
        # Ma trận Data: Lưu Khối lượng ('w') và Số cuộn ('c') cho từng ô C1-C6
        matrix = {g: {k: {f"C{i}": {'w': 0.0, 'c': 0} for i in range(1, 7)} for k in keys} for g, keys in DEFECT_GROUPS.items()}
        
        # Ma trận Base: Lưu tổng khối lượng (Mẫu số) cho từng lỗi để chia %
        base_weights = {g: {k: 0.0 for k in keys} for g, keys in DEFECT_GROUPS.items()}

        # 4. QUÉT VÀ PHÂN BỔ DỮ LIỆU TỪNG CUỘN THÉP
        for r in rows:
            # Ưu tiên lấy Ca từ DB, nếu NULL thì nội suy từ thời gian
            actual_shift = str(r['Ca']).strip() if r['Ca'] else ''
            if shift_filter != 'ALL' and actual_shift != shift_filter:
                continue

            kpis['total_coils'] += 1
            w = float(r['weight']) if r['weight'] else 0.0
            
            # Cuộn chưa cân -> Đếm vào Cảnh báo KPI, KHÔNG đưa vào tính % Heatmap
            if w <= 0:
                kpis['missing_weight'] += 1
                continue 

            kpis['total_weight'] += w
            scores = json.loads(r['scores']) if r['scores'] else {}
            p_status = str(r['prime_status']).strip().upper() if r['prime_status'] else ''
            qc_status = str(r['qc_status']).strip().upper() if r['qc_status'] else ''
            order_id = r['Order']

            if qc_status == 'PASS':
                if p_status == 'PRIME':
                    kpis['w_prime_pass'] += w
                elif p_status == 'NON_PRIME':
                    kpis['w_nonprime_pass'] += w
                elif p_status == 'SCRAP':
                    kpis['w_scrap_pass'] += w
            
            elif qc_status == 'PASSNOCHEM':
                if p_status == 'PRIME':
                    kpis['w_surf_pass_nochem'] += w
                    
            elif qc_status == 'PENDING':
                if not order_id or str(order_id).strip() == '' or str(order_id).strip().upper() == 'NONE':
                    kpis['w_unassigned_pending'] += w
            elif qc_status in ['FAIL', 'FAILNOCHEM']:
                kpis['w_processing'] += w
            # Kiểm tra xem cuộn có kết quả Cơ tính từ Lab chưa
            has_mech = any(scores.get(k, 0) > 0 for k in ['YieldPoint', 'Tensile', 'Elongation', 'Hardness'])
            if not has_mech:
                kpis['missing_mech'] += 1

            for group_name, keys in DEFECT_GROUPS.items():
                # Bỏ qua hoàn toàn nhóm Cơ tính nếu Lab chưa có kết quả (Tránh làm nhiễu mẫu số)
                if group_name == 'PROP' and not has_mech:
                    continue

                for key in keys:
                    base_weights[group_name][key] += w 
                    
                    # Lấy điểm, nếu key không tồn tại trong JSON thì mặc định coi như Đạt (C1)
                    score_val = int(float(scores.get(key, 0)))
                    c_level = f"C{score_val}" if 1 <= score_val <= 6 else "C1"
                    
                    # Cộng dồn Khối lượng và Tăng biến đếm Số cuộn
                    matrix[group_name][key][c_level]['w'] += w
                    matrix[group_name][key][c_level]['c'] += 1

        # 5. CHUYỂN ĐỔI THÀNH PHẦN TRĂM (%) VÀ ĐỊNH DẠNG RESPONSE
        response_matrix = {g: {} for g in DEFECT_GROUPS.keys()}
        
        for g, keys in DEFECT_GROUPS.items():
            for k in keys:
                total_w = base_weights[g][k]
                response_matrix[g][k] = {}
                
                for c_level in range(1, 7):
                    c_key = f"C{c_level}"
                    data = matrix[g][k][c_key]
                    
                    # Tính % (Tránh lỗi chia cho 0)
                    pct = round((data['w'] / total_w) * 100, 1) if total_w > 0 else 0.0
                    
                    response_matrix[g][k][c_key] = {
                        'pct': pct,
                        'weight': int(round(data['w'], 0)), # Cắt bỏ phần thập phân, ép kiểu số nguyên
                        'count': data['c']                  # Gửi số cuộn lên cho Tooltip
                    }

        # 6. TRẢ KẾT QUẢ VỀ FRONTEND
        return jsonify({
            'status': 'success', 
            'kpis': kpis, 
            'matrix': response_matrix
        })

    except Exception as e:
        import traceback
        traceback.print_exc() # In chi tiết lỗi ra Terminal server để dễ debug
        return jsonify({'status': 'error', 'msg': str(e)})
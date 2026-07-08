from flask import Blueprint, render_template, request, jsonify
import db

qc_dash_bp = Blueprint('qc_dash_bp', __name__)

@qc_dash_bp.route('/qc_dashboard_order', methods=['GET'])
def qc_dashboard_page():
    return render_template('qc_dashboard_order.html')

# API 1: Lấy danh sách tổng hợp từ View
@qc_dash_bp.route('/api/qc/order_summary', methods=['GET'])
def get_order_summary():
    conn = None
    try:
        conn = db.get_connection()
        cursor = conn.cursor()
        
        # Lấy data từ view
        cursor.execute("SELECT * FROM vw_QC_Order_Summary ORDER BY [Order] DESC")
        rows = db.fetchall_as_dict(cursor)
        
        # Tính toán thông số tổng (Overview Cards)
        total_target = sum(r['Target_Weight'] for r in rows)
        total_actual = sum(r['Actual_Weight'] for r in rows)
        total_pass = sum(r['Pass_Weight'] for r in rows)
        
        global_progress = round((total_actual / total_target * 100), 1) if total_target > 0 else 0
        global_pass_rate = round((total_pass / total_actual * 100), 1) if total_actual > 0 else 0

        return jsonify({
            'status': 'success',
            'overview': {
                'target': total_target,
                'actual': total_actual,
                'progress_pct': global_progress,
                'pass_rate_pct': global_pass_rate
            },
            'data': rows
        })
    except Exception as e:
        return jsonify({'status': 'error', 'msg': str(e)})
    finally:
        if conn: conn.close()

# API 2: Drill-down bóc tách chuỗi lỗi
@qc_dash_bp.route('/api/qc/order_errors/<order_id>', methods=['GET'])
def get_order_errors(order_id):
    conn = None
    try:
        conn = db.get_connection()
        cursor = conn.cursor()
        
        # Chỉ lấy các cuộn FAIL của Order này
        cursor.execute("""
            SELECT weight, qc_msg 
            FROM coil_data 
            WHERE LTRIM(RTRIM([Order])) = ? AND qc_status = 'FAIL' AND qc_msg IS NOT NULL
        """, (str(order_id).strip(),))
        
        fail_coils = db.fetchall_as_dict(cursor)
        
        error_stats = {}
        for coil in fail_coils:
            msg = str(coil['qc_msg'])
            weight = float(coil['weight'] or 0)
            
            # Tách chuỗi: "Xỉ sơ cấp HP:C4(Lệch 1), Khuyết biên:Thiếu"
            errors = [e.strip() for e in msg.split(',')]
            for err in errors:
                if not err: continue
                # Lấy tên lỗi trước dấu hai chấm
                defect_name = err.split(':')[0].strip() if ':' in err else err
                if "Khối lượng" in defect_name:
                    defect_name = "Lỗi Khối lượng"
                # Cộng dồn khối lượng rớt
                error_stats[defect_name] = error_stats.get(defect_name, 0) + weight

        # Sort lấy Top lỗi nhiều nhất
        sorted_errors = sorted(error_stats.items(), key=lambda x: x[1], reverse=True)
        
        labels = [x[0] for x in sorted_errors]
        data = [x[1] for x in sorted_errors]

        return jsonify({'status': 'success', 'labels': labels, 'data': data})
    except Exception as e:
        return jsonify({'status': 'error', 'msg': str(e)})
    finally:
        if conn: conn.close()
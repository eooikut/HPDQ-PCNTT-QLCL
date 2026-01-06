from flask import Blueprint, app, render_template, current_app, request, jsonify
import threading
import json
import db  # Module db.py
from apscheduler.schedulers.background import BackgroundScheduler
alloc_hist_bp = Blueprint('alloc_hist_bp', __name__)
upload_lock = threading.Lock()

@alloc_hist_bp.route('/allocation_history', methods=['GET'])
def allocation_history_page():
    return render_template('allocation_history.html')


@alloc_hist_bp.route('/api/get_history_summary', methods=['GET'])
def get_history_summary():
    try:
        conn = db.get_connection()
        
        # 1. Lấy danh sách Đơn hàng (Header) kèm tổng yêu cầu (Target)
        # Join sales_orders với so_details để tính tổng Tấn/Cuộn yêu cầu
        orders_query = """
            SELECT 
                so.so_number, 
                so.customer_name, 
                so.order_date,
                SUM(d.total_weight) as target_weight,
                SUM(d.qty) as target_qty
            FROM sales_orders so
            LEFT JOIN so_details d ON so.id = d.so_id
            GROUP BY so.id
            ORDER BY so.created_at DESC
        """
        cursor = conn.cursor()
        cursor.execute(orders_query)
        orders_rows = db.fetchall_as_dict(cursor)
        
        # 2. Lấy số liệu thực tế đang phân bổ (Actual) từ coil_data
        # Group by SO để tính tổng
        actual_query = """
            SELECT 
                allocated_order, 
                COUNT(*) as actual_qty, 
                SUM(weight) as actual_weight
            FROM coil_data WITH (NOLOCK) 
            WHERE allocated_order IS NOT NULL AND allocated_order != ''
            GROUP BY allocated_order
        """
        cursor.execute(actual_query)
        actual_rows = db.fetchall_as_dict(cursor)
        actual_map = {r['allocated_order']: dict(r) for r in actual_rows}

        # 3. Ghép dữ liệu Header + Actual
        orders = []
        for r in orders_rows:
            so = r['so_number']
            act = actual_map.get(so, {'actual_qty': 0, 'actual_weight': 0})
            
            orders.append({
                'so_number': so,
                'customer_name': r['customer_name'],
                'date': r['order_date'],
                'target_weight': r['target_weight'] or 0,
                'target_qty': r['target_qty'] or 0,
                'actual_weight': act['actual_weight'] or 0,
                'actual_qty': act['actual_qty'] or 0
            })

        # 4. Lấy chi tiết cuộn (Để hiển thị bên phải màn hình khi click)
        # Lấy thêm scores để vẽ radar nếu cần
        cursor.execute("""
            SELECT coil_id, allocated_order, weight, target_thick, target_width, scores, grade 
            FROM coil_data WITH (NOLOCK) 
            WHERE allocated_order IS NOT NULL AND allocated_order != ''
        """)
        coils_rows = db.fetchall_as_dict(cursor) # <--- SỬA
        
        # Chuyển row thành dict và parse scores JSON
        coils = []
        for r in coils_rows:
            item = dict(r)
            item['scores'] = json.loads(item['scores']) if item['scores'] else {}
            coils.append(item)
            
        conn.close()
        return jsonify({'orders': orders, 'coils': coils})

    except Exception as e:
        print(e)
        return jsonify({'orders': [], 'coils': [], 'msg': str(e)})
@alloc_hist_bp.route('/api/release_coils', methods=['POST'])
def release_coils():
    try:
        req = request.json
        coil_ids = req.get('coil_ids', [])
        
        if not coil_ids: return jsonify({'status': 'error', 'msg': 'Chưa chọn cuộn nào'})
        
        conn = db.get_connection()
        # Update về NULL để trả về kho
        for cid in coil_ids:
            conn.execute("UPDATE coil_data SET allocated_to = NULL, allocated_order = NULL, allocated_at = NULL WHERE coil_id = ?", (cid,))
        conn.commit()
        conn.close()
        
        return jsonify({'status': 'success', 'msg': f'Đã gỡ {len(coil_ids)} cuộn.'})
    except Exception as e: return jsonify({'status': 'error', 'msg': str(e)})

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
@alloc_hist_bp.route('/api/get_allocated_data', methods=['GET'])
def get_allocated_data():
    try:
        conn = db.get_connection()
        # Lấy các cuộn đã được gán (allocated_to không null)
        rows = conn.execute("""
            SELECT * FROM coil_data 
            WHERE allocated_to IS NOT NULL AND allocated_to != '' 
            ORDER BY allocated_at DESC
        """).fetchall()
        conn.close()
        
        result = []
        for r in rows:
            result.append({
                'customer': r['allocated_to'],
                'so_number': r['allocated_order'] or 'Chưa gán SO', # Lấy SO từ DB
                'coil_id': r['coil_id'],
                'grade': r['grade'],
                'weight': r['weight'] or 0,
                'thick': r['target_thick'] or 0,
                'width': r['target_width'] or 0,
                'scores': json.loads(r['scores']) if r['scores'] else {},
                'allocated_at': r['allocated_at']
            })
            
        return jsonify(result)
    except Exception as e: return jsonify([])
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

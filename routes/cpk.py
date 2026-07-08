from flask import Blueprint, render_template, request, jsonify
import db
import json
import pandas as pd
import numpy as np

cpk_bp = Blueprint('cpk_bp', __name__)

# --- CẤU HÌNH TIÊU CHUẨN ---
DEFAULT_SPECS = {
    'Flatness':    {'label': 'Độ phẳng (IU)', 'usl': 20, 'lsl': 0, 'type': 'geometry', 'is_abs': True},
    'Crown':       {'label': 'Độ Crown (µm)', 'usl': 50, 'lsl': 0, 'type': 'geometry', 'is_abs': True},
    'Wedge':       {'label': 'Độ Wedge (µm)', 'usl': 30, 'lsl': 0, 'type': 'geometry', 'is_abs': True},
    'ThickDiff':   {'label': 'Sai lệch Dày', 'usl': 0.05, 'lsl': 0, 'type': 'geometry', 'is_abs': True},
    'WidthDiff':   {'label': 'Sai lệch Rộng', 'usl': 20, 'lsl': 0, 'type': 'geometry', 'is_abs': True},
    'Temperature': {'label': 'Nhiệt độ FT', 'usl': 890, 'lsl': 870, 'type': 'geometry', 'is_abs': False},
    'Speed':       {'label': 'Nhiệt độ tạo cuộn', 'usl': 700, 'lsl': 680, 'type': 'geometry', 'is_abs': False},
    'YieldPoint': {'label': 'Giới hạn chảy', 'usl': 320, 'lsl': 170, 'type': 'mechanical'},
    'Tensile':    {'label': 'Giới hạn bền', 'usl': 400, 'lsl': 295, 'type': 'mechanical'},
    'Elongation': {'label': 'Độ giãn dài (%)', 'usl': 50, 'lsl': 30, 'type': 'mechanical'},
    'Hardness':   {'label': 'Độ cứng (HRB)', 'usl': 70, 'lsl': 50, 'type': 'mechanical'},
    'C':  {'label': 'C (%)', 'usl': 0.06, 'lsl': 0.02, 'type': 'chemical'},
    'Mn': {'label': 'Mn (%)', 'usl': 0.20, 'lsl': 0.15, 'type': 'chemical'},
    'Si': {'label': 'Si (%)', 'usl': 0.03, 'lsl': 0, 'type': 'chemical'},
    'P':  {'label': 'P (%)', 'usl': 0.02, 'lsl': 0, 'type': 'chemical'},
    'S':  {'label': 'S (%)', 'usl': 0.01, 'lsl': 0, 'type': 'chemical'},
}

@cpk_bp.route('/cpk_dashboard')
def cpk_page():
    try:
        conn = db.get_connection()
        cursor = conn.cursor()
        
        # 1. Lấy Nhà máy
        cursor.execute("SELECT DISTINCT factory FROM coil_data WHERE factory IS NOT NULL")
        factories = [r[0] for r in cursor.fetchall()]
        
        # 2. Xây dựng cây phân cấp: Grade -> Slab -> {Targets}
        query_map = """
            SELECT DISTINCT grade, slab_grade_name, target_temp_finish, target_temp_coil
            FROM coil_data 
            WHERE grade IS NOT NULL 
              AND slab_grade_name IS NOT NULL
            ORDER BY grade, slab_grade_name, target_temp_finish
        """
        cursor.execute(query_map)
        rows = cursor.fetchall()
        
        # Structure: { 'SS400': { 'L080A': { 'ft': [850, 870], 'ct': [600, 620] } } }
        hierarchy = {}
        
        for r in rows:
            grade = r[0]
            slab = r[1]
            ft = r[2] # Finishing Temp Target
            ct = r[3] # Coiling Temp Target
            
            if grade not in hierarchy: 
                hierarchy[grade] = {}
            
            if slab not in hierarchy[grade]:
                hierarchy[grade][slab] = {'ft': set(), 'ct': set()}
            
            if ft is not None: hierarchy[grade][slab]['ft'].add(ft)
            if ct is not None: hierarchy[grade][slab]['ct'].add(ct)

        # Convert sets to sorted lists for JSON serialization
        for g in hierarchy:
            for s in hierarchy[g]:
                hierarchy[g][s]['ft'] = sorted(list(hierarchy[g][s]['ft']))
                hierarchy[g][s]['ct'] = sorted(list(hierarchy[g][s]['ct']))

        conn.close()
    except Exception as e:
        print(f"DB Error: {e}")
        factories = ['HRC1']
        hierarchy = {}

    return render_template('cpk_dashboard.html', 
                           factories=factories, 
                           hierarchy=hierarchy, # Truyền cây dữ liệu xuống Client
                           default_specs=DEFAULT_SPECS)

@cpk_bp.route('/api/cpk/data', methods=['POST'])
def get_cpk_data():
    try:
        req = request.json
        factory = req.get('factory', 'HRC1')
        grade = req.get('grade')
        slab_grade = req.get('slab_grade')
        
        # --- Nhận Target cụ thể (Exact Match) ---
        target_ft = req.get('target_ft') 
        target_ct = req.get('target_ct') 
        
        start_date = req.get('start_date')
        end_date = req.get('end_date')
        thick_min = float(req.get('thick_min') or 0)
        thick_max = float(req.get('thick_max') or 999)

        query = """
            SELECT TOP 100000
                coil_id, production_date, raw_data, Temperature, Speed 
            FROM coil_data WITH (NOLOCK)
            WHERE factory = ? 
            AND target_thick >= ? AND target_thick <= ?
        """
        params = [factory, thick_min, thick_max]

        if grade:
            query += " AND grade = ?"
            params.append(grade)
        
        if slab_grade:
            query += " AND slab_grade_name = ?"
            params.append(slab_grade)

        # --- LỌC EXACT MATCH CHO TARGET TEMP ---
        if target_ft:
            query += " AND target_temp_finish = ?"
            params.append(float(target_ft))
            
        if target_ct:
            query += " AND target_temp_coil = ?"
            params.append(float(target_ct))
        # ---------------------------------------

        if start_date and end_date:
            query += " AND production_date BETWEEN ? AND ?"
            params.append(start_date)
            params.append(end_date)
        
        query += " ORDER BY production_date ASC"

        engine = db.get_db_engine()
        with engine.connect() as conn:
            df_sql = pd.read_sql(query, conn, params=tuple(params))

        if df_sql.empty:
            return jsonify({'status': 'success', 'count': 0, 'data': {}})

        # --- PANDAS PROCESS ---
        def parse_safe(x):
            try: return json.loads(x) if x else {}
            except: return {}
            
        json_data = list(df_sql['raw_data'].apply(parse_safe))
        df_json = pd.DataFrame(json_data)

        if 'Temperature' in df_sql.columns: df_json['Temperature'] = df_sql['Temperature']
        if 'Speed' in df_sql.columns: df_json['Speed'] = df_sql['Speed']
        df_json['coil_id'] = df_sql['coil_id']
        
        # Convert datetime sang string để tránh lỗi JSON serializable
        if 'production_date' in df_sql.columns:
            df_json['production_date'] = df_sql['production_date'].astype(str)
        else:
            df_json['production_date'] = ''
        extracted_data = {}
        for key, spec in DEFAULT_SPECS.items():
            if key not in df_json.columns:
                extracted_data[key] = {'values': [], 'ids': [], 'dates': []}
                continue
            temp_df = df_json[[key, 'coil_id', 'production_date']].copy()
            
            # Chuyển sang numeric, lỗi thành NaN
            temp_df[key] = pd.to_numeric(temp_df[key], errors='coerce')
            
            # Lọc ABS nếu cần
            if spec.get('is_abs', False): 
                temp_df[key] = temp_df[key].abs()
            temp_df = temp_df.dropna(subset=[key])
            if spec['type'] in ['mechanical', 'chemical']: 
                temp_df = temp_df[temp_df[key] > 0]
            extracted_data[key] = {
                'values': temp_df[key].tolist(),
                'ids': temp_df['coil_id'].tolist(),
                'dates': temp_df['production_date'].tolist()
            }

        return jsonify({'status': 'success', 'count': len(df_sql), 'data': extracted_data})

    except Exception as e:
        import traceback
        traceback.print_exc()
        return jsonify({'status': 'error', 'message': str(e)}), 500

# ========================================
# CUSTOM USL/LSL PERSISTENCE APIS
# ========================================

@cpk_bp.route('/api/cpk/custom_limits', methods=['GET'])
def get_custom_limits():
    """
    Get custom USL/LSL for given filter combination
    Query params: factory, grade, slab_grade_name, thickness, thickness_max,
                  target_temp_finish, target_temp_coil
    """
    conn = None
    try:
        factory = request.args.get('factory')
        grade = request.args.get('grade')
        slab_grade = request.args.get('slab_grade_name')
        thickness = float(request.args.get('thickness', 0))
        thickness_max = float(request.args.get('thickness_max', 0))
        temp_finish = int(request.args.get('target_temp_finish', 0))
        temp_coil = int(request.args.get('target_temp_coil', 0))
        
        conn = db.get_connection()
        cursor = conn.cursor()
        
        query = """
            SELECT spec_key, usl, lsl
            FROM cpk_custom_limits
            WHERE factory = ? 
              AND grade = ?
              AND slab_grade_name = ?
              AND thickness = ?
              AND thickness_max = ?
              AND target_temp_finish = ?
              AND target_temp_coil = ?
        """
        
        cursor.execute(query, (factory, grade, slab_grade, thickness, thickness_max,
                              temp_finish, temp_coil))
        rows = cursor.fetchall()
        
        # Convert to dict: {spec_key: {usl, lsl}}
        custom_limits = {}
        for row in rows:
            custom_limits[row[0]] = {
                'usl': row[1],
                'lsl': row[2]
            }
        return jsonify({'status': 'success', 'data': custom_limits})
        
    except Exception as e:
        import traceback
        traceback.print_exc()
        return jsonify({'status': 'error', 'message': str(e)}), 500
    finally:
        if conn: conn.close()

@cpk_bp.route('/api/cpk/custom_limits', methods=['POST'])
def save_custom_limit():
    """
    Save/Update custom USL/LSL
    Body: {
        factory, grade, slab_grade_name, thickness,
        target_temp_finish, target_temp_coil,
        spec_key, usl, lsl, updated_by
    }
    """
    conn = None
    try:
        data = request.get_json()
        
        factory = data['factory']
        grade = data['grade']
        slab_grade = data['slab_grade_name']
        thickness = float(data['thickness'])
        thickness_max = float(data['thickness_max'])
        temp_finish = int(data['target_temp_finish'])
        temp_coil = int(data['target_temp_coil'])
        spec_key = data['spec_key']
        usl = data.get('usl')
        lsl = data.get('lsl')
        updated_by = data.get('updated_by', 'system')
        
        conn = db.get_connection()
        cursor = conn.cursor()
        
        # MERGE (upsert) logic
        merge_query = """
            MERGE cpk_custom_limits AS target
            USING (SELECT ? AS factory, ? AS grade, ? AS slab_grade_name,
                         ? AS thickness, ? AS thickness_max, ? AS target_temp_finish, 
                         ? AS target_temp_coil, ? AS spec_key) AS source
            ON (target.factory = source.factory
                AND target.grade = source.grade
                AND target.slab_grade_name = source.slab_grade_name
                AND target.thickness = source.thickness
                AND target.thickness_max = source.thickness_max
                AND target.target_temp_finish = source.target_temp_finish
                AND target.target_temp_coil = source.target_temp_coil
                AND target.spec_key = source.spec_key)
            WHEN MATCHED THEN
                UPDATE SET usl = ?, lsl = ?, 
                          updated_by = ?, updated_at = GETDATE()
            WHEN NOT MATCHED THEN
                INSERT (factory, grade, slab_grade_name, thickness, thickness_max,
                       target_temp_finish, target_temp_coil, spec_key,
                       usl, lsl, updated_by)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?);
        """
        
        cursor.execute(merge_query, (
            factory, grade, slab_grade, thickness, thickness_max, temp_finish, temp_coil, spec_key,
            usl, lsl, updated_by,
            factory, grade, slab_grade, thickness, thickness_max, temp_finish, temp_coil, spec_key,
            usl, lsl, updated_by
        ))
        
        conn.commit()
        
        
        return jsonify({'status': 'success', 'message': 'Custom limit saved'})
        
    except Exception as e:
        import traceback
        traceback.print_exc()
        return jsonify({'status': 'error', 'message': str(e)}), 500
    finally:
        if conn: conn.close()

@cpk_bp.route('/api/cpk/custom_limits', methods=['DELETE'])
def delete_custom_limit():
    """
    Delete custom limit - revert to default
    Body: {
        factory, grade, slab_grade_name, thickness,
        target_temp_finish, target_temp_coil, spec_key
    }
    """
    conn = None
    try:
        data = request.get_json()
        
        conn = db.get_connection()
        cursor = conn.cursor()
        
        delete_query = """
            DELETE FROM cpk_custom_limits
            WHERE factory = ? AND grade = ? AND slab_grade_name = ?
              AND thickness = ? AND thickness_max = ?
              AND target_temp_finish = ?
              AND target_temp_coil = ? AND spec_key = ?
        """
        
        cursor.execute(delete_query, (
            data['factory'], data['grade'], data['slab_grade_name'],
            float(data['thickness']), float(data['thickness_max']),
            int(data['target_temp_finish']),
            int(data['target_temp_coil']), data['spec_key']
        ))
        
        conn.commit()
        
        return jsonify({'status': 'success', 'message': 'Custom limit deleted'})
        
    except Exception as e:
        import traceback
        traceback.print_exc()
        return jsonify({'status': 'error', 'message': str(e)}), 500
    finally:
        if conn: conn.close()


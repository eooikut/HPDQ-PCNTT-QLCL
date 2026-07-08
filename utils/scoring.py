from utils.common import sanitize_data, desanitize_data
import pandas as pd
import numpy as np
from utils.constants import DEFAULT_CONFIG_TEMPLATE
import db  # Module db.py

from apscheduler.schedulers.background import BackgroundScheduler


import time
MANUAL_DEFECT_KEYS = [
    # Surface Manual
    'oil', 'rust', 'scratch_m', 'dirt','other_s', 'gianbien','chambi','dungsaitrong',
    # Geo Manual
    'telescope', 'high_spot',
    
]
def calculate_score_from_raw(raw_val, config_item):
    try:
        # --- BƯỚC 1: CHUẨN HÓA DỮ LIỆU ĐẦU VÀO ---
        sizes = []
        mode = config_item.get('mode')
        group = config_item.get('group') # Lấy nhóm để phân loại xử lý
        # --- A. XỬ LÝ MODE VALUE (HÌNH HỌC, CƠ, LÝ, HÓA) ---
        if mode == 'value':
            # 1. Kiểm tra rỗng/None
            is_empty = (raw_val is None) or (raw_val == '')
            # 2. Kiểm tra NaN (nếu là số đặc biệt)
            if not is_empty:
                try:
                    import math
                    if isinstance(raw_val, float) and math.isnan(raw_val): is_empty = True
                    # Check numpy nan nếu cần thiết
                except: pass

            # 3. NẾU RỖNG THÌ TRẢ VỀ ĐIỂM MẶC ĐỊNH NGAY
            if is_empty:
                # [QUAN TRỌNG] Cơ/Lý/Hóa thiếu data -> Về 0 (C0 - Chưa có)
                if group in ['mechanical', 'chemical']: 
                    return 0
                # Hình học thiếu data -> Về 1 (C1 - Mặc định tốt/Bỏ qua)
                return 1 

            # 4. Nếu có dữ liệu, thử convert sang float để tính toán
            try:
                val = float(raw_val)
                sizes = [val] 
            except:
                # Nếu lỗi convert (VD: chuỗi rác) -> Xử lý như rỗng
                if group in ['mechanical', 'chemical']: return 0
                return 1

        # --- B. XỬ LÝ MODE MATRIX/COUNT (BỀ MẶT) ---
        else:
            if isinstance(raw_val, list):
                # Lọc bỏ giá trị None/Empty trong list
                for x in raw_val:
                    try:
                        if x is not None and x != '': sizes.append(float(x))
                        else: sizes.append(0.0)
                    except: sizes.append(0.0)
            elif raw_val is None or raw_val == '':
                return 1 
            else:
                try:
                    # Nếu là số đơn (VD: nhập tay số lượng lỗi)
                    count = int(raw_val) 
                    sizes = [0.0] * count # Tạo list dummy để đếm số lượng
                except:
                    sizes = []
        
        # Nếu sau khi xử lý mà không có size nào (cho trường hợp Bề mặt) -> Về 1
        if not sizes: return 1 

        # --- BƯỚC 2: TÍNH ĐIỂM (LOGIC GỐC - QUAN TRỌNG KHÔNG ĐƯỢC XÓA) ---
        
        # 1. MODE MATRIX
        if mode == 'matrix':
            bins = config_item['bins']
            count_limits = config_item['count_limits']
            matrix = config_item['matrix_rules']
            
            bin_counts = {}
            for s in sizes:
                for i in range(len(bins)-1):
                    if bins[i] < s <= bins[i+1]:
                        bin_counts[i] = bin_counts.get(i, 0) + 1
                        break
            
            final_score = 1
            for row_idx, count in bin_counts.items():
                if row_idx >= len(matrix): continue
                col_idx = 0
                for c_idx, limit in enumerate(count_limits):
                    if count <= limit:
                        col_idx = c_idx
                        break
                
                current_row_scores = matrix[row_idx]
                if col_idx < len(current_row_scores):
                    score = current_row_scores[col_idx]
                    final_score = max(final_score, score)
            return final_score

        # 2. MODE COUNT
        elif mode == 'count':
            threshold = config_item.get('threshold', 5)
            scores_map = config_item['scores_high'] if len(sizes) > threshold else config_item['scores_low']
            bins = config_item['bins']
            max_score = 1
            
            for s in sizes:
                for i in range(len(bins)-1):
                    if bins[i] < s <= bins[i+1]:
                        if i < len(scores_map): 
                            val_mapped = scores_map[i]
                            if val_mapped == 0: val_mapped = 1
                            max_score = max(max_score, val_mapped)
                        break
            return max_score

        # 3. MODE VALUE (QUAN TRỌNG CHO HÌNH HỌC/CƠ LÝ)
        elif mode == 'value':
             val = sizes[0]
             if config_item.get('use_abs'): val = abs(val)
             
             bins = config_item['bins']
             scores = config_item.get('scores_value', [1,2,3,4,5,6])
             
             for i in range(len(bins)-1):
                 # Logic mới chuẩn theo ban hành: [biên_dưới, biên_trên)
                 # Tức là: >= biên dưới VÀ < biên trên
                 if bins[i] <= val < bins[i+1]:
                     if i < len(scores): return scores[i]
             # Nếu vượt quá bin cuối cùng -> C6
             return 6 

    except Exception as e:
        print(f"Error calc score: {e}")
        # Gặp lỗi không xác định -> Về an toàn (1) hoặc 0 tùy logic, ở đây để 1
        return 1
    
    return 1
def get_all_grade_configs():
    cfgs = db.get_config('grade_configs')
    if not cfgs:
        cfgs = desanitize_data(DEFAULT_CONFIG_TEMPLATE)
        db.save_config('grade_configs', sanitize_data(cfgs))
    else:
        cfgs = desanitize_data(cfgs)
    return cfgs
def process_coil_scores(coil_id, raw_data, grade, thickness=0.0, cached_config=None):
    if cached_config:
        all_configs = cached_config
    else:
        all_configs = get_all_grade_configs()
    
    grade_config = all_configs.get(grade, all_configs.get('SAE1006'))
    if not grade_config: return {}
    
    scores = {}
    
    # 1. TÍNH ĐIỂM GỐC: Tính toán bình thường dựa trên config
    for key, cfg in grade_config.items():
        val = raw_data.get(key, None)
        scores[key] = calculate_score_from_raw(val, cfg)
        
    # ------------------------------------------------------------------
    # 2. XỬ LÝ THÔNG MINH CHO CÁC CHỈ TIÊU TÙY CHỌN (O, H, N, Cu, Ni...)
    # ------------------------------------------------------------------
    # Kiểm tra xem cuộn này ĐÃ ĐƯỢC TEST TPHH / Cơ lý chưa? 
    # (Chỉ cần có 1 chất > 0 là chứng tỏ đã qua Lab)
    has_chemical_data = any(
        grade_config.get(k, {}).get('group') == 'chemical' and scores[k] > 0 
        for k in scores
    )
    
    has_mechanical_data = any(
        grade_config.get(k, {}).get('group') == 'mechanical' and scores[k] > 0 
        for k in scores
    )
    curr_grade = str(grade).upper()
    IMPACT_GRADES = [
        'Q355B', 'J55', 
        'S235JR', 'S235J0', 'S235J2', 
        'S275JR', 'S275J0', 'S275J2', 
        'S355JR', 'S355J0', 'S355J2'
    ]
    is_impact_grade = any(g in curr_grade for g in IMPACT_GRADES)

    # --- BƯỚC 2.1: XỬ LÝ ĐỘC LẬP IMPACT ENERGY ---
    # Dùng .get() để lấy điểm. Nếu config không khai báo, nó tự hiểu là 0
    if scores.get('ImpactEnergy', 0) == 0:
        if is_impact_grade and thickness > 6.0:
            scores['ImpactEnergy'] = 0  # Bắt buộc chờ Lab đo (C0)
        else:
            scores['ImpactEnergy'] = 1  # Mặc định Pass (C1)

    # --- BƯỚC 2.2: QUÉT THÔNG MINH CÁC CHỈ TIÊU CÒN LẠI ---
    # Dùng list(scores.keys()) để duyệt an toàn nếu dictionary có biến động
    for k in list(scores.keys()):
        if k == 'ImpactEnergy':
            continue  # Đã xử lý triệt để ở Bước 2.1
            
        if scores[k] == 0:
            grp = grade_config.get(k, {}).get('group')
            
            # Nếu đã test TPHH, nhưng chất này thiếu -> Mặc định C1 (Pass)
            if grp == 'chemical' and has_chemical_data:
                scores[k] = 1
                
            # Nếu đã test Cơ lý, nhưng mục này thiếu -> Mặc định C1 (Pass)
            elif grp == 'mechanical' and has_mechanical_data:
                scores[k] = 1

    # 3. Tự động gán C1 cho các lỗi THỦ CÔNG (Bề mặt nhập bằng tay)
    for m_key in MANUAL_DEFECT_KEYS:
        if m_key not in scores:
            if m_key in raw_data and raw_data[m_key] is not None:
                try:
                    scores[m_key] = float(raw_data[m_key])
                except:
                    scores[m_key] = 1
            else:
                # Mặc định C1 (Tốt)
                scores[m_key] = 1
    scores['is_thick_pass'] = -1
    return scores
def calculate_metric_surface(df, name, config, total_rolls):
    default_result = {'summary': [], 'details': [], 'matrix': [], 'col_headers': [], 'total': 0}

    
    try:
        target = config.get('target_defect', name)
        
        # --- 1. CHUẨN BỊ DỮ LIỆU ---
        raw_labels = config['labels']
        
        # Helper: Hiển thị (Reverse order for chart usually)
        display_sizes = []
        seen = set()
        for l in reversed(raw_labels): 
            if l not in seen: display_sizes.append(l); seen.add(l)

        # Cấu hình
        matrix_rules = config.get('matrix_rules', [])
        count_limits_cfg = config.get('count_limits', [])
        heatmap_cols = config.get('heatmap_cols', [])
        col_headers = [r[2] for r in heatmap_cols]

        # --- 2. XỬ LÝ DỮ LIỆU (VECTORIZED) ---
        df_defect = pd.DataFrame()
        if 'DefectClass' in df.columns:
            df_defect = df[df['DefectClass'] == target].copy()
            
            df_defect['Size'] = pd.to_numeric(df_defect['Size'], errors='coerce').fillna(0.0)

            # LỌC LỖI NHỎ: Bỏ qua tất cả lỗi có kích thước nhỏ hơn hoặc bằng mốc bắt đầu của bins
            min_size = config['bins'][0]
            df_defect = df_defect[df_defect['Size'] > min_size]

            df_defect['SizeLabel'] = pd.cut(df_defect['Size'], bins=config['bins'], labels=config['labels'], right=True, include_lowest=True).astype(str)

        if df_defect.empty: 
            return {
                'summary': [], 'details': [], 
                'matrix': [{'SizeName': sz, 'Cells': [{'Count':0,'Percent':0,'Class':'C0','CoilList':''} for _ in heatmap_cols]} for sz in display_sizes],
                'col_headers': col_headers, 'total': total_rolls
            }

        # --- 3. COUNT PER SIZE ---

        counts_df = df_defect.groupby(['CustomerID', 'SizeLabel'], observed=True).size().reset_index(name='DefectCount')
        counts_df = counts_df[counts_df['DefectCount'] > 0]
        
        if counts_df.empty:
            return {
                'summary': [], 'details': [], 
                'matrix': [{'SizeName': sz, 'Cells': [{'Count':0,'Percent':0,'Class':'C0','CoilList':''} for _ in heatmap_cols]} for sz in display_sizes],
                'col_headers': col_headers, 'total': total_rolls
            }

        # --- 4. MAP TO SCORES (VECTORIZED) ---
        
        # A. Map Label -> Row Index
        label_to_idx = {l: i for i, l in enumerate(raw_labels)}
        counts_df['RowIdx'] = counts_df['SizeLabel'].map(label_to_idx).fillna(-1).astype(int)
        
        # B. Map Count -> Col Index (Relative to Matrix Rules)
        if config.get('mode') == 'matrix':
            # Create logic to mapping Count -> ColIdx
            limits_arr = np.array(count_limits_cfg)
            
            col_idxs = np.searchsorted(limits_arr, counts_df['DefectCount'].values, side='left')
            counts_df['ColIdx'] = col_idxs
            
            # C. Lookup Score from Matrix
            try:
                # Fill jagged with max score (6) just in case
                max_len = max(len(r) for r in matrix_rules) if matrix_rules else 0
                matrix_np = np.full((len(matrix_rules), max_len), 6)
                for r_i, r_data in enumerate(matrix_rules):
                    for c_i, val in enumerate(r_data):
                        matrix_np[r_i, c_i] = val
                
                # Clip indices to avoid out of bounds
                r_indices = np.clip(counts_df['RowIdx'].values, 0, matrix_np.shape[0]-1)
                c_indices = np.clip(counts_df['ColIdx'].values, 0, matrix_np.shape[1]-1)
                
                counts_df['Score'] = matrix_np[r_indices, c_indices]
                
            except:
                # Fallback to apply if matrix construction fails
                def get_matrix_score(row):
                    try:
                        r = matrix_rules[row['RowIdx']]
                        idx = row['ColIdx']
                        return r[idx] if idx < len(r) else r[-1]
                    except: return 1
                counts_df['Score'] = counts_df.apply(get_matrix_score, axis=1)

        elif config.get('mode') == 'count':
            # Count Mode: High/Low Threshold
            threshold = config.get('threshold', 5)
            # Map RowIdx -> Score High/Low arrays
            # scores_high, scores_low correspond to raw_labels indices
            
            # Prepare lookup arrays (Pad with 1 if missing)
            s_high_arr = np.array(config.get('scores_high', [1]*len(raw_labels)))
            s_low_arr = np.array(config.get('scores_low', [1]*len(raw_labels)))
            
            # Create mask for High/Low
            is_high = counts_df['DefectCount'] > threshold
            
            # Lookup
            # Careful with RowIdx out of bounds (should not happen if mapped correctly)
            safe_row_idx = np.clip(counts_df['RowIdx'].values, 0, len(s_high_arr)-1)
            
            scores_col = np.where(is_high, s_high_arr[safe_row_idx], s_low_arr[safe_row_idx])
            counts_df['Score'] = scores_col
            
        else:
            # Fallback
            counts_df['Score'] = 1

        # --- 5. FIND WINNER PER COIL (VECTORIZED) ---
        counts_df = counts_df.sort_values(by=['CustomerID', 'Score', 'DefectCount'], ascending=[True, False, False])
        coil_status_df = counts_df.drop_duplicates(subset=['CustomerID']).copy()
        coil_status_map = coil_status_df.set_index('CustomerID')[['Score', 'SizeLabel', 'DefectCount']].to_dict('index')

        # --- 6. PREPARE DETAILS (Total Count per Coil) ---
        total_counts = counts_df.groupby('CustomerID')['DefectCount'].sum()
        
        details_list = []
        heatmap_map = {sz: {i: [] for i in range(len(heatmap_cols))} for sz in display_sizes}
        coil_status_df['Total'] = coil_status_df['CustomerID'].map(total_counts)
        coil_status_df['MatrixCol'] = 0
        crit_counts = coil_status_df['DefectCount'].values
        
        for c_idx, (start, end, _) in enumerate(heatmap_cols):
            # Mask for current bin
            mask = (crit_counts >= start) & (crit_counts <= end)
            if start == 0 and end == 0: # Check specifically for 0
                 # Usually counts_df only has >0. 
                 # 0-count entries (C1) handle later.
                 pass
            
            coil_status_df.loc[mask, 'MatrixCol'] = c_idx
        for _, row in coil_status_df.iterrows():
            cid = row['CustomerID']
            sz = str(row['SizeLabel'])
            sc = row['Score']
            cnt = row['DefectCount'] # Critical Count
            total = row['Total']
            col_idx = row['MatrixCol']
            
            # Add to details
            details_list.append({
                'Cuộn': cid,
                'Loại': f"C{sc}",
                'RadarScore': sc,
                'Total': int(total),
                'CriticalLabel': sz,
                'DetailCounts': {} 
            })
            
            # Add to Heatmap buckets
            if sz in heatmap_map and col_idx in heatmap_map[sz]:
                heatmap_map[sz][col_idx].append(cid)
        detail_dicts = counts_df.groupby('CustomerID')[['SizeLabel', 'DefectCount']].apply(
            lambda x: dict(zip(x['SizeLabel'], x['DefectCount']))
        ).to_dict()
        
        # Merge into details_list
        for d in details_list:
            d['DetailCounts'] = detail_dicts.get(d['Cuộn'], {})

        # --- 7. HANDLE CLEAN COILS ---
        processed_count = len(coil_status_df)
        remaining_count = total_rolls - processed_count
        target_col_idx = 0
        if remaining_count > 0:
            for c_idx, (start, end, _) in enumerate(heatmap_cols):
                if start == 0: target_col_idx = c_idx; break
            
            if display_sizes:
                smallest_sz = display_sizes[-1]
                if smallest_sz in heatmap_map:
                    heatmap_map[smallest_sz][target_col_idx].extend(["..."] * min(remaining_count, 1)) 


        # --- 8. RENDER HEATMAP ---
        matrix_data = []
        for sz in display_sizes:
            row_obj = {'SizeName': sz, 'Cells': []}
            # Determine Row Rule Index for coloring
            try: row_idx_rule = raw_labels.index(sz)
            except: row_idx_rule = -1
            
            for col_idx, (start, end, _) in enumerate(heatmap_cols):
                coils_in_cell = heatmap_map.get(sz, {}).get(col_idx, [])
                
                # Manual Count Fix for Remainder
                count_in_cell = len(coils_in_cell)
                
                # If this is the "Clean Cell", add the remaining count
                is_clean_cell = (sz == display_sizes[-1] and col_idx == target_col_idx)
                if is_clean_cell:
                    count_in_cell = len(coils_in_cell) + (remaining_count if 'remaining_count' in locals() else 0)
                    # Coil list doesn't get the IDs, but count is correct.
                
                # Check Logic for Class Color (C1-C6)
                # Same as original
                c_val_int = 1
                if start > 0: 
                    if config.get('mode') == 'matrix' and row_idx_rule != -1:
                        # Logic to find which limit bin 'end' falls into
                        target_limit_idx = 0
                        for c_limit_idx, limit in enumerate(count_limits_cfg):
                            if end <= limit: target_limit_idx = c_limit_idx; break
                            target_limit_idx = c_limit_idx
                        
                        if row_idx_rule < len(matrix_rules) and target_limit_idx < len(matrix_rules[row_idx_rule]):
                            c_val_int = matrix_rules[row_idx_rule][target_limit_idx]

                    elif config.get('mode') == 'count' and row_idx_rule != -1:
                         score_tbl = config.get('scores_high') if 'scores_high' in config else []
                         c_val_int = score_tbl[row_idx_rule] if row_idx_rule < len(score_tbl) else 1

                coil_str = ""
                if count_in_cell > 0 and not is_clean_cell:
                     coil_str = ",".join(coils_in_cell[:100])
                
                row_obj['Cells'].append({
                    'Count': count_in_cell,
                    'Percent': round(count_in_cell/total_rolls*100, 1) if total_rolls > 0 else 0,
                    'Class': f"C{c_val_int}",
                    'CoilList': coil_str
                })
            matrix_data.append(row_obj)

        # 5. KẾT QUẢ
        details_list.sort(key=lambda x: (x['Loại'], x['Total']), reverse=True)
        summary_counts = pd.DataFrame(details_list)['Loại'].value_counts().to_dict() if details_list else {}
        
        # Add C1/Clean count to summary
        if 'remaining_count' in locals() and remaining_count > 0:
            summary_counts['C1'] = summary_counts.get('C1', 0) + remaining_count

        summary_data = [{'Loại': k, 'Số Cuộn': v, 'Tỉ lệ': round(v/total_rolls*100, 2)} for k, v in summary_counts.items()]
        summary_data.sort(key=lambda x: x['Loại'])

        final_result = {
            'summary': summary_data,
            'details': details_list, # Note: This misses clean coils details, but that's standard for Exception Reporting
            'matrix': matrix_data,
            'col_headers': col_headers,
            'total': total_rolls
        }
        return sanitize_data(final_result)

    except Exception as e:
        print(f"Err Surf Vectorized {name}: {e}")
        import traceback; traceback.print_exc()
        return default_result
# Tính toán metric dạng Giá Trị (Cơ/Lý/Hóa)
def calculate_metric_value(df, name, config, total_rolls, score_lookup=None):
    default_result = {'summary': [], 'details': [], 'matrix': [], 'col_headers': [], 'total': 0}
    try:
        # 1. XÁC ĐỊNH LABEL HIỂN THỊ
        raw_labels = config.get('labels', [])
        if not raw_labels: return default_result
        
        display_sizes = []
        seen = set()
        for l in reversed(raw_labels):
            if l not in seen: display_sizes.append(l); seen.add(l)

        target_label_c1 = raw_labels[0] 
        if 'scores_value' in config and 1 in config['scores_value']:
            try:
                idx_c1 = config['scores_value'].index(1)
                if idx_c1 < len(raw_labels):
                    target_label_c1 = raw_labels[idx_c1]
            except: pass

        # 3. LẤY GIÁ TRỊ THÔ (GIỮ NGUYÊN)
        col_vals = pd.Series(0, index=df.index)
        if name in df.columns: 
            col_vals = pd.to_numeric(df[name], errors='coerce')
        
        results = []
        
        #  Để theo dõi những cuộn CÓ DỮ LIỆU THỰC SỰ
        valid_data_ids = set() 

        # 4. DUYỆT QUA TỪNG CUỘN (Vectorized)
        score = 0
        if score_lookup:
             scores_only = {k: v.get(name, 0) for k, v in score_lookup.items()}
             df_scores = df['CustomerID'].map(scores_only).fillna(0).astype(int)
        else:
             df_scores = pd.Series(0, index=df.index)

        # Create DataFrame for filtering
        res_df = pd.DataFrame({
            'Cuộn': df['CustomerID'],
            'Val': col_vals,
            'RadarScore': df_scores
        })
        err_df = res_df[res_df['RadarScore'] > 1].copy()
        
        # Calculate C_LABEL for errors
        if not err_df.empty:
            score_to_label = {}
            if 'scores_value' in config:
                for idx, sc in enumerate(config['scores_value']):
                    lbl = raw_labels[idx] if idx < len(raw_labels) else f"C{sc}"
                    score_to_label[sc] = lbl
            else:
                # Fallback: Score 1->Label 0
                for s in range(1, 10):
                    idx = s - 1
                    lbl = raw_labels[idx] if idx < len(raw_labels) else f"C{s}"
                    score_to_label[s] = lbl
            
            err_df['Loại'] = err_df['RadarScore'].map(score_to_label).fillna("C?")
            err_df['CriticalLabel'] = err_df['Loại']
            err_df['Total'] = 1
            err_df['DetailCounts'] = err_df.apply(
                lambda r: {r['Loại']: round(r['Val'], 4) if isinstance(r['Val'], float) else r['Val']}, 
                axis=1
            )
            
            results = err_df[['Cuộn', 'Loại', 'RadarScore', 'Total', 'CriticalLabel', 'DetailCounts']].to_dict('records')
        else:
            results = []
        # 5. XỬ LÝ DANH SÁCH CUỘN TỐT (CÓ SỬA ĐỔI)
        valid_mask = (res_df['RadarScore'] > 0) & (pd.notna(res_df['Val']))
        valid_data_ids = set(res_df[valid_mask]['Cuộn'].unique())

        defect_ids = {r['Cuộn'] for r in results} if results else set()
        non_defect_ids = list(valid_data_ids - defect_ids)
        
        c0_items = []
        for cid in non_defect_ids:
            # Cuộn tốt: Total = 0
            c0_items.append({
                'Cuộn': cid, 'Loại': target_label_c1, 
                'RadarScore': 1, 'Total': 0, 
                'CriticalLabel': target_label_c1, 'DetailCounts': {}
            })
        
        full_details = results + c0_items
        full_details.sort(key=lambda x: (x['RadarScore'], x['Total']), reverse=True)

        # Summary Table 
        df_full = pd.DataFrame(full_details)
        summary_counts = df_full['Loại'].value_counts().to_dict() if not df_full.empty else {}
        summary_data = [{'Loại': k, 'Số Cuộn': v, 'Tỉ lệ': round(v / total_rolls * 100, 2) if total_rolls > 0 else 0} for k, v in summary_counts.items() if v > 0]
        summary_data.sort(key=lambda x: x['Loại'])

        # 6. VẼ MATRIX (HEATMAP) 
        matrix_data = []
        col_ranges = config.get('heatmap_cols', [(1, 1, 'C1')]) 
        col_headers = [r[2] for r in col_ranges]

        for sz in display_sizes: 
            row_obj = {'SizeName': sz, 'Cells': []}
            
            subset = pd.DataFrame()
            if not df_full.empty:
                subset = df_full[df_full['Loại'] == sz]
            
            for start, end, _ in col_ranges:
                cnt = 0
                coils = []
                is_c1_cell = (sz == target_label_c1 and start <= 1)
                
                if is_c1_cell:
                    cnt += len(non_defect_ids)
                    coils += non_defect_ids
                
                if not subset.empty:
                    in_range = subset[(subset['Total'] >= start) & (subset['Total'] <= end)]
                    cnt += len(in_range)
                    coils += in_range['Cuộn'].astype(str).tolist()
                c_val_int = 1
                try:
                    if 'scores_value' in config and sz in raw_labels:
                        idx = raw_labels.index(sz)
                        if idx < len(config['scores_value']):
                            c_val_int = config['scores_value'][idx]
                    else:
                        if sz in raw_labels: c_val_int = raw_labels.index(sz) + 1
                except: pass
                if cnt == 0: c_val_int = 0

                coil_str = ",".join(coils[:100])
                row_obj['Cells'].append({
                    'Count': cnt, 
                    'Percent': round(cnt/total_rolls*100, 1) if total_rolls > 0 else 0, 
                    'Class': f"C{c_val_int}", 
                    'CoilList': coil_str
                })
            
            matrix_data.append(row_obj)
        
        return {'summary': summary_data, 'details': full_details, 'matrix': matrix_data, 'col_headers': col_headers, 'total': total_rolls}
    except Exception as e:
        print(f"Err Val {name}: {e}")
        return default_result
def calculate_metric_single(df, name, config, total_rolls):
    default_result = {'summary': [], 'details': [], 'matrix': [], 'col_headers': [], 'total': 0}
    try:
        raw_labels = config['labels']
        display_sizes = []
        seen = set()
        for l in reversed(raw_labels):
            if l not in seen:
                display_sizes.append(l)
                seen.add(l)
        # LOGIC BỀ MẶT (COUNT)
        if config.get('mode') == 'count':
            target = config.get('target_defect', name)
            if 'DefectClass' not in df.columns: return default_result
            
            df_defect = df[df['DefectClass'] == target].copy()
            df_defect['Size'] = df_defect['Size'].fillna(0)
            df_defect['SizeLabel'] = pd.cut(df_defect['Size'], bins=config['bins'], labels=config['labels'], right=True, include_lowest=True)
            
            if df_defect.empty: matrix = pd.DataFrame()
            else: matrix = pd.crosstab(df_defect['CustomerID'], df_defect['SizeLabel'])

            results = []
            final_scores = pd.Series(1, index=matrix.index)
            
            if not matrix.empty:
                matrix['Total'] = matrix.sum(axis=1)
                mask_high = matrix['Total'] > config['threshold']
                
                for idx, label in enumerate(config['labels']):
                    if label in matrix.columns:
                        s_low = config['scores_low'][idx] if idx < len(config['scores_low']) else 1
                        s_high = config['scores_high'][idx] if idx < len(config['scores_high']) else 1
                        # Fix 0->1
                        if s_low == 0: s_low = 1
                        if s_high == 0: s_high = 1
                        
                        has_defect = matrix[label] > 0
                        score_series = pd.Series(s_low, index=matrix.index)
                        score_series[mask_high] = s_high
                        
                        update_mask = has_defect & (score_series >= final_scores)
                        if update_mask.any():
                            final_scores.loc[update_mask] = score_series.loc[update_mask]
            
            defect_cids = final_scores.index.tolist()
            for cid in defect_cids:
                score_val = final_scores[cid]
                c_code = f"C{score_val}" # C1..C6
                detail_counts = {}
                if cid in matrix.index:
                    row_data = matrix.loc[cid].to_dict()
                    row_data.pop('Total', None)
                    detail_counts = {k: v for k, v in row_data.items() if v > 0}
                results.append({'Cuộn': cid, 'Loại': c_code, 'RadarScore': int(score_val), 'Total': sum(detail_counts.values()), 'CriticalLabel': c_code, 'DetailCounts': detail_counts})

        # LOGIC VALUE (VALUE)
        else:
            col_vals = pd.Series(0, index=df.index)
            if name in df.columns: col_vals = pd.to_numeric(df[name], errors='coerce').fillna(0)
            if config.get('use_abs'): col_vals = col_vals.abs()
            labels_map = pd.cut(col_vals, bins=config['bins'], labels=config['labels'], include_lowest=True, ordered=False)
            scores_raw = pd.cut(col_vals, bins=config['bins'], labels=config['scores_value'], include_lowest=True, ordered=False).astype(float).fillna(1).astype(int)
            
            df_temp = pd.DataFrame({'CustomerID': df['CustomerID'], 'Label': labels_map, 'RawScore': scores_raw})
            df_temp = df_temp.sort_values('RawScore', ascending=False).drop_duplicates(subset=['CustomerID'], keep='first')
            df_error = df_temp[df_temp['RawScore'] > 1] 
            
            results = []
            for _, row in df_error.iterrows():
                c_code = f"C{int(row['RawScore'])}"
                lbl = str(row['Label'])
                results.append({'Cuộn': row['CustomerID'], 'Loại': c_code, 'RadarScore': int(row['RawScore']), 'Total': 1, 'CriticalLabel': lbl, 'DetailCounts': {lbl: 1}})

        # --- PHẦN 2: TỔNG HỢP DATA ---
        defect_ids = {r['Cuộn'] for r in results}
        all_ids = set(df['CustomerID'].unique())
        non_defect_ids = list(all_ids - defect_ids)
        
        c0_items = []
        # Tìm label ứng với điểm 1 (C1)
        target_label_c1 = config['labels'][0]
        if 'scores_value' in config:
            try: target_label_c1 = config['labels'][config['scores_value'].index(1)]
            except: pass
        
        for cid in non_defect_ids:
            c0_items.append({'Cuộn': cid, 'Loại': 'C1', 'RadarScore': 1, 'Total': 0, 'CriticalLabel': target_label_c1, 'DetailCounts': {}})
        
        full_details = results + c0_items
        full_details.sort(key=lambda x: (x['Loại'], x['Total']), reverse=True)

        df_full = pd.DataFrame(full_details)
        
        # Tạo Summary Table
        summary_counts = df_full['Loại'].value_counts().to_dict() if not df_full.empty else {}
        summary_data = [{'Loại': k, 'Số Cuộn': v, 'Tỉ lệ': round(v / total_rolls * 100, 2) if total_rolls > 0 else 0} for k, v in summary_counts.items() if v > 0]
        summary_data.sort(key=lambda x: x['Loại'])

        # --- PHẦN 3: VẼ HEATMAP MATRIX (ĐÃ FIX LOGIC LỌC) ---
        matrix_data = []
        col_ranges = config['heatmap_cols']
        col_headers = [r[2] for r in col_ranges]

        # Loop qua từng dòng của Heatmap (display_sizes = 0-1000, 1001-1500... HOẶC C6, C5...)
        for sz in display_sizes: 
            row_obj = {'SizeName': sz, 'Cells': []}
            subset = pd.DataFrame()
            if not df_full.empty:
                if config.get('mode') == 'count':
                    if not df_defect.empty:
                        # Tìm các cuộn có SizeLabel == sz
                        match_ids = df_defect[df_defect['SizeLabel'] == sz]['CustomerID'].unique()
                        subset = df_full[df_full['Cuộn'].isin(match_ids)]
                else:
                    # Nếu là Value (Hình học/Cơ lý): Lọc theo CriticalLabel hoặc Loại
                    if sz == 'C6': subset = df_full[df_full['Loại'].astype(str).str.contains('C6')]
                    # Với WidthDiff, nhãn là C6, C1... nên lọc theo CriticalLabel
                    elif sz in df_full['CriticalLabel'].values:
                        subset = df_full[df_full['CriticalLabel'] == sz]
                    else:
                        subset = df_full[df_full['Loại'] == sz]

            for start, end, _ in col_ranges:
                cnt = 0
                coils = []
                if not subset.empty:
                    in_range = subset[(subset['Total'] >= start) & (subset['Total'] <= end)]
                    
                    # Logic cộng bù C1 (Tốt)
                    is_c1_cell = False
                    if config.get('mode') == 'count':
                        # Surface: C1 là ô [0 lỗi] của nhãn đầu tiên
                        if start == 0 and sz == config['labels'][0]: is_c1_cell = True
                    else:
                        # Value: C1 là ô [Total=0] của nhãn C1
                        if start <= 1 and sz == target_label_c1: is_c1_cell = True
                    
                    if is_c1_cell:
                        cnt += len(non_defect_ids)
                        coils += non_defect_ids

                    cnt += len(in_range)
                    coils += in_range['Cuộn'].astype(str).tolist()

                # Tính màu (Color Class)
                c_val_int = 0 # Mặc định xanh (bg-C0)
                if sz in config['labels']:
                    idx = config['labels'].index(sz)
                    if config.get('mode') == 'count':
                        score_tbl = config['scores_high'] if start > config['threshold'] else config['scores_low']
                        raw_score = score_tbl[idx] if idx < len(score_tbl) else 1
                    else:
                        raw_score = config['scores_value'][idx]
                    
                    c_val_int = max(0, raw_score - 1)
                
                coil_str = ",".join(coils[:100])
                row_obj['Cells'].append({'Count': cnt, 'Percent': round(cnt/total_rolls*100, 1) if total_rolls > 0 else 0, 'Class': f"C{c_val_int}", 'CoilList': coil_str})
            
            matrix_data.append(row_obj)

        return {'summary': summary_data, 'details': full_details, 'matrix': matrix_data, 'col_headers': col_headers, 'total': total_rolls}

    except Exception as e:
        print(f"Err {name}: {e}")
        return default_result
def build_final_response_optimized(defect_list, config, total_rolls, count_c0, c0_display_list=None):
    df_defect = pd.DataFrame(defect_list)
    summary_counts = {}
    if not df_defect.empty: summary_counts = df_defect['Loại'].value_counts().to_dict()
    if count_c0 > 0: summary_counts['C0'] = summary_counts.get('C0', 0) + count_c0
    summary_data = [{'Loại': k, 'Số Cuộn': v, 'Tỉ lệ': round(v / total_rolls * 100, 2) if total_rolls > 0 else 0} for k, v in summary_counts.items() if v > 0]
    summary_data.sort(key=lambda x: x['Loại'])

    c0_items = []
    # Tìm nhãn đại diện cho C0 thực sự (có điểm score=1) để hiển thị
    # Nếu không tìm thấy, fallback về nhãn đầu tiên
    first_label = config['labels'][0]
    if 'scores_value' in config:
        try:
            # Tìm index của điểm 1 (C0)
            c0_idx = config['scores_value'].index(1)
            first_label = config['labels'][c0_idx]
        except: pass

    if c0_display_list:
        for cid in c0_display_list:
            c0_items.append({'Cuộn': cid, 'Loại': 'C0', 'Total': 0, 'CriticalLabel': first_label, 'DetailCounts': {}})
    
    full_details = defect_list + c0_items
    full_details.sort(key=lambda x: (x['Loại'], x['Total']), reverse=True)

    matrix_data = []
    display_sizes = list(reversed(config['labels']))
    col_ranges = config['heatmap_cols']
    col_headers = [r[2] for r in col_ranges]
    
    # Xác định label nào được tính là C0 để cộng bù số lượng
    target_label_c0 = config['labels'][0]
    if config.get('mode') == 'value':
        # Tìm label ứng với điểm 1 (C0)
        if 'scores_value' in config:
            try:
                c0_idx = config['scores_value'].index(1)
                target_label_c0 = config['labels'][c0_idx]
            except: pass

    for sz in display_sizes:
        row_obj = {'SizeName': sz, 'Cells': []}
        subset = pd.DataFrame()
        if not df_defect.empty: subset = df_defect[df_defect['CriticalLabel'] == sz]
        
        for start, end, _ in col_ranges:
            cnt = 0
            coils = []
            if not subset.empty:
                in_range = subset[(subset['Total'] >= start) & (subset['Total'] <= end)]
                cnt = len(in_range)
                coils = in_range['Cuộn'].astype(str).tolist()
            
            is_c0_cell = False
            if config.get('mode') == 'count':
                # Surface: C0 là ô [0 lỗi] của nhãn đầu tiên (thường là range thấp nhất)
                if start == 0 and sz == config['labels'][0]: is_c0_cell = True
            else:
                # Value: C0 là ô [Total=1] của nhãn C0 (Target Label)
                if start == 1 and sz == target_label_c0: is_c0_cell = True
            
            if is_c0_cell:
                cnt += count_c0
                if c0_display_list: coils = c0_display_list + coils
            c_val = 0 
            if sz in config['labels']:
                idx = config['labels'].index(sz)
                
                # Logic lấy điểm (1-6)
                if config.get('mode') == 'count':
                    score_tbl = config['scores_high'] if start > config['threshold'] else config['scores_low']
                    raw_score = score_tbl[idx] if idx < len(score_tbl) else 1
                else:
                    # Value Mode
                    if 'scores_value' in config and idx < len(config['scores_value']):
                        raw_score = config['scores_value'][idx]
                    else:
                        raw_score = idx + 1 # Fallback cũ
                c_val = max(0, raw_score - 1)

            coil_str = ",".join(coils[:100]) if len(coils) > 100 else ",".join(coils)
            row_obj['Cells'].append({
                'Count': cnt, 
                'Percent': round(cnt/total_rolls*100, 1) if total_rolls > 0 else 0, 
                'Class': f"C{c_val}", # Class màu sẽ đúng: C5_L (điểm 6) -> C5 (Đỏ)
                'CoilList': coil_str
            })
            
        matrix_data.append(row_obj)
    return {'summary': summary_data, 'details': full_details, 'matrix': matrix_data, 'col_headers': col_headers, 'total': total_rolls}
    
import json

def evaluate_tdc_stage_1(scores_json, criteria_json, coil_weight, min_w, max_w):
    """
    ĐÁNH GIÁ GIAI ĐOẠN 1 (DÙNG CHO DASHBOARD): Kích thước, Khối lượng và Bề mặt.
    Dùng để tính lại điểm tức thì khi KCS sửa lỗi trên giao diện.
    """
    STAGE_2_DEFECTS = ['YieldPoint', 'Tensile', 'Elongation', 'Hardness', 'ImpactEnergy', 'C', 'Mn', 'Si', 'P', 'S', 'Cu', 'Ni', 'Cr', 'Mo', 'V', 'Ti', 'Al', 'Ca', 'B', 'Nb', 'CEV', 'O', 'N', 'H']
    coil_weight = float(coil_weight) if coil_weight is not None else 0.0
    try:
        scores = json.loads(scores_json) if scores_json else {}
        criteria_list = json.loads(criteria_json) if criteria_json else []
    except Exception:
        return {'stage1_penalty': 9999, 'stage1_msg': 'Lỗi JSON', 'status': 'FAILNOCHEM'}

    penalty = 0
    failed_reasons = []
    is_thick_pass = scores.get('is_thick_pass', -1) # Mặc định là 0 (Không đạt)
    if is_thick_pass == -1:
        penalty += 999  
        failed_reasons.append("CHƯA ĐÁNH GIÁ CHIỀU DÀY")
    elif is_thick_pass == 0:
        penalty += 100
        failed_reasons.append("Chiều dày không đạt")
    if min_w > 0 and coil_weight < min_w:
        penalty += 100
        failed_reasons.append(f"Khối lượng ({coil_weight}) < Min ({min_w})")
    if max_w > 0 and coil_weight > max_w:
        penalty += 100
        failed_reasons.append(f"Khối lượng ({coil_weight}) > Max ({max_w})")

    TOTAL_CRITERIA_COUNT = len(criteria_list)
    for idx, crit in enumerate(criteria_list):
        defect_key = crit['defect']
        if defect_key in STAGE_2_DEFECTS: continue 
            
        val = scores.get(defect_key, 0)
        allowed_range = crit.get('range', [])
        weight_score = TOTAL_CRITERIA_COUNT - idx 
        
        if val == 0: 
            penalty += (weight_score * 25)
            failed_reasons.append(f"{crit.get('name_vi', defect_key)}:Thiếu")
        elif allowed_range and val not in allowed_range:
            closest_limit = min(allowed_range, key=lambda x: abs(x - val))
            dist = abs(val - closest_limit)
            penalty += (weight_score * dist * 5)
            failed_reasons.append(f"{crit.get('name_vi', defect_key)}:C{val}(Lệch {dist})")

    return {
        'stage1_penalty': penalty,
        'stage1_msg': ', '.join(failed_reasons) if failed_reasons else "Đạt",
        'status': 'PASSNOCHEM' if penalty == 0 else 'FAILNOCHEM'
    }
# scoring.py
STAGE_2_DEFECTS = ['YieldPoint', 'Tensile', 'Elongation', 'Hardness', 'ImpactEnergy', 'C', 'Mn', 'Si', 'P', 'S', 'Cu', 'Ni', 'Cr', 'Mo', 'V', 'Ti', 'Al', 'Ca', 'B', 'Nb', 'CEV', 'O', 'N', 'H']
def evaluate_tdc_stage_2(scores_json, criteria_json):
    """
    Hàm này phải khớp 100% với logic chấm điểm Stage 2 hiện tại 
    đang nằm trong các hàm của bạn.
    """
    try:
        scores = json.loads(scores_json) if isinstance(scores_json, str) else scores_json
        criteria_list = json.loads(criteria_json) if isinstance(criteria_json, str) else criteria_json
    except Exception:
        return {'stage2_penalty': 9999, 'stage2_msg': 'Lỗi JSON'}

    penalty = 0
    failed_reasons = []
    
    # Duyệt criteria và chấm điểm cơ tính/hóa học giống như cách bạn đã làm
    for idx, crit in enumerate(criteria_list):
        defect_key = crit['defect']
        # Chỉ chấm các lỗi thuộc STAGE_2_DEFECTS
        if defect_key not in STAGE_2_DEFECTS: continue 
            
        val = scores.get(defect_key, 0)
        allowed_range = crit.get('range', [])
        
        # Logic tính penalty cũ (trọng số * khoảng cách * 5)
        if val == 0: 
            penalty += ((len(criteria_list) - idx) * 25)
            failed_reasons.append(f"{crit.get('name_vi', defect_key)}:Thiếu")
        elif allowed_range and val not in allowed_range:
            closest_limit = min(allowed_range, key=lambda x: abs(x - val))
            # 1. Tính toán khoảng cách (dist) ra một biến riêng giống hệt stage 1
            dist = abs(val - closest_limit) 
            
            # 2. Tính penalty dựa trên biến dist
            penalty += ((len(criteria_list) - idx) * dist * 5)
            
            # 3. Nối thêm (Lệch {dist}) vào chuỗi thông báo
            failed_reasons.append(f"{crit.get('name_vi', defect_key)}:C{val}(Lệch {dist})")

    return {
        'stage2_penalty': penalty,
        'stage2_msg': ', '.join(failed_reasons) if failed_reasons else ""
    }
def build_matrix_tooltip(sizes, config_item):
    """
    Hàm phân tích sizes và trả về mảng chuỗi format: 'SL: x | Size: y-z | Cx'
    """
    if not isinstance(sizes, list) or not sizes:
        return ["Không có lỗi"]

    # Lọc rác và convert float
    clean_sizes = []
    for x in sizes:
        try:
            if x is not None and x != '': clean_sizes.append(float(x))
        except: pass

    if not clean_sizes: return ["Không có lỗi"]

    mode = config_item.get('mode')
    
    # 1. Nếu là Mode Matrix (Lỗi tự động có ma trận)
    if mode == 'matrix':
        bins = config_item.get('bins', [])
        count_limits = config_item.get('count_limits', [])
        matrix = config_item.get('matrix_rules', [])
        
        # Đếm size vào bins
        bin_counts = {}
        for s in clean_sizes:
            for i in range(len(bins)-1):
                if bins[i] < s <= bins[i+1]:
                    bin_counts[i] = bin_counts.get(i, 0) + 1
                    break
        
        details = []
        # Quét từng nhóm bin có data để tìm điểm
        for row_idx, count in bin_counts.items():
            if row_idx >= len(matrix): continue
            
            # Tìm cột giới hạn số lượng
            col_idx = 0
            for c_idx, limit in enumerate(count_limits):
                if count <= limit:
                    col_idx = c_idx
                    break
            
            # Lấy điểm C
            current_row_scores = matrix[row_idx]
            score = current_row_scores[col_idx] if col_idx < len(current_row_scores) else 6
            
            # Tạo chuỗi hiển thị
            size_range = f"{bins[row_idx]}~{bins[row_idx+1]}"
            details.append(f"SL: {count} | Size: {size_range} | C{score}")
        
        # Sort theo điểm C tệ nhất đưa lên đầu
        details.sort(key=lambda x: x[-2:], reverse=True)
        return details

    # 2. Nếu là Mode đếm thông thường (Count) hoặc nhập tay
    else:
        mx = max(clean_sizes)
        return [f"SL: {len(clean_sizes)} | Max Size: {mx:.2f}"] 
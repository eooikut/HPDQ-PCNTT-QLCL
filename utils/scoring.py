from utils.common import sanitize_data, desanitize_data
import pandas as pd
from utils.constants import DEFAULT_CONFIG_TEMPLATE
import db  # Module db.py

from apscheduler.schedulers.background import BackgroundScheduler


import time
MANUAL_DEFECT_KEYS = [
    # Surface Manual
    'oil', 'rust', 'scratch_m', 'dirt', 'mark', 'scale', 'other_s', 'gianbien',
    # Geo Manual
    'telescope'
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
                 # Bin đầu tiên: Lấy cả biên dưới
                 if i == 0:
                     if bins[i] <= val <= bins[i+1]:
                         if i < len(scores): return scores[i]
                 else:
                     # Các bin sau: Lớn hơn biên dưới
                     if bins[i] < val <= bins[i+1]:
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
def process_coil_scores(coil_id, raw_data, grade, cached_config=None):
    if cached_config:
        all_configs = cached_config
    else:
        all_configs = get_all_grade_configs()
    grade_config = all_configs.get(grade, all_configs.get('SAE1006'))
    if not grade_config: return {}
    
    scores = {}
    
    # 1. Tính điểm cho các chỉ số CÓ TRONG CONFIG (Sẽ vẽ Heatmap)
    for key, cfg in grade_config.items():
        val = raw_data.get(key, None)
        scores[key] = calculate_score_from_raw(val, cfg)
        
    # 2. [THÊM MỚI] Tự động gán C1 cho các lỗi THỦ CÔNG (Không vẽ Heatmap)
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

    return scores
def calculate_metric_surface(df, name, config, total_rolls):
    """
    Heatmap Bề Mặt (FINAL V4 - FULL DETAILS & FIX BUGS):
    1. Heatmap: Dùng logic 'Winner Takes All' (Chỉ xếp vào ô lỗi nặng nhất).
    2. Bảng chi tiết: Hiển thị TOÀN BỘ các lỗi.
    3. Fix lỗi: Đã khai báo default_result.
    """
    default_result = {'summary': [], 'details': [], 'matrix': [], 'col_headers': [], 'total': 0}
    
    try:
        target = config.get('target_defect', name)
        
        # --- 1. CHUẨN BỊ DỮ LIỆU ---
        raw_labels = config['labels']
        display_sizes = []
        seen = set()
        for l in reversed(raw_labels): 
            if l not in seen: display_sizes.append(l); seen.add(l)

        # Cấu hình
        matrix_rules = config.get('matrix_rules', [])
        count_limits = config.get('count_limits', [])
        heatmap_cols = config.get('heatmap_cols', [])
        col_headers = [r[2] for r in heatmap_cols]

        all_coil_ids = set(df['CustomerID'].unique()) if 'CustomerID' in df.columns else set()

        # Lọc dữ liệu lỗi
        df_defect = pd.DataFrame()
        if 'DefectClass' in df.columns:
            df_defect = df[df['DefectClass'] == target].copy()
            # Fix size rỗng -> 1.0
            df_defect['Size'] = pd.to_numeric(df_defect['Size'], errors='coerce').fillna(1.0)
            df_defect['SizeLabel'] = pd.cut(df_defect['Size'], bins=config['bins'], labels=config['labels'], right=True, include_lowest=True)

        # Bảng tổng hợp đếm: Index=[CoilID], Cols=[SizeLabels]
        if df_defect.empty: matrix_counts = pd.DataFrame()
        else: matrix_counts = pd.crosstab(df_defect['CustomerID'], df_defect['SizeLabel'])

        # --- 2. TÍNH TOÁN "WINNER" ĐỂ VẼ HEATMAP ---
        final_coil_status = {} # Map: coil_id -> {Score, CriticalSize, CriticalCount}

        if not df_defect.empty:
            counts_per_size = df_defect.groupby(['CustomerID', 'SizeLabel'], observed=True).size()
            
            for coil_id in df_defect['CustomerID'].unique():
                best_score = 1
                best_size = raw_labels[0]
                best_count = 0
                
                # Duyệt tìm lỗi nặng nhất
                for label_idx, label in enumerate(config['labels']):
                    try: cnt = counts_per_size.get((coil_id, label), 0)
                    except: cnt = 0
                    
                    if cnt > 0:
                        current_score = 1
                        if config.get('mode') == 'matrix' and label_idx < len(matrix_rules):
                            row_rules = matrix_rules[label_idx]
                            for c_idx, limit in enumerate(count_limits):
                                if cnt <= limit:
                                    current_score = row_rules[c_idx] if c_idx < len(row_rules) else row_rules[-1]
                                    break
                            else: current_score = row_rules[-1]
                        
                        elif config.get('mode') == 'count':
                             s_high = config['scores_high'][label_idx] if 'scores_high' in config else 1
                             s_low = config['scores_low'][label_idx] if 'scores_low' in config else 1
                             current_score = s_high if cnt > config.get('threshold', 5) else s_low

                        if current_score >= best_score:
                            best_score = current_score
                            best_size = label
                            best_count = cnt
                
                final_coil_status[coil_id] = {'Score': best_score, 'CriticalSize': best_size, 'CriticalCount': best_count}

        # Xử lý cuộn sạch
        for cid in all_coil_ids:
            if cid not in final_coil_status:
                final_coil_status[cid] = {'Score': 1, 'CriticalSize': config['labels'][0], 'CriticalCount': 0}

        # --- 3. TẠO LIST CHI TIẾT ---
        details_list = []
        heatmap_map = {sz: {i: [] for i in range(len(heatmap_cols))} for sz in display_sizes}

        for cid, status in final_coil_status.items():
            sc = status['Score']
            crit_sz = status['CriticalSize']
            crit_cnt = status['CriticalCount']
            
            # Lấy chi tiết TẤT CẢ các lỗi
            full_detail_counts = {}
            if cid in matrix_counts.index:
                row_data = matrix_counts.loc[cid]
                for col_name, val in row_data.items():
                    if val > 0:
                        full_detail_counts[str(col_name)] = int(val)
            
            details_list.append({
                'Cuộn': cid,
                'Loại': f"C{sc}",
                'RadarScore': sc,
                'Total': sum(full_detail_counts.values()), 
                'CriticalLabel': crit_sz,
                'DetailCounts': full_detail_counts
            })
            
            # Map vào Heatmap
            if crit_sz in heatmap_map:
                for col_idx, (start, end, _) in enumerate(heatmap_cols):
                    if start <= crit_cnt <= end:
                        heatmap_map[crit_sz][col_idx].append(cid)
                        break
                    elif crit_cnt == 0 and start == 0:
                        heatmap_map[crit_sz][col_idx].append(cid)
                        break

        # Gom cuộn sạch còn sót
        for cid, status in final_coil_status.items():
            if status['CriticalCount'] == 0:
                found = False
                for sz in heatmap_map:
                    for c_idx in heatmap_map[sz]:
                        if cid in heatmap_map[sz][c_idx]: found = True; break
                if not found and display_sizes:
                    heatmap_map[display_sizes[-1]][0].append(cid)

        # --- 4. RENDER HEATMAP ---
        matrix_data = []
        for sz in display_sizes:
            row_obj = {'SizeName': sz, 'Cells': []}
            try: row_idx_rule = raw_labels.index(sz)
            except: row_idx_rule = -1
            
            for col_idx, (start, end, _) in enumerate(heatmap_cols):
                coils_in_cell = list(set(heatmap_map.get(sz, {}).get(col_idx, [])))
                count_in_cell = len(coils_in_cell)
                
                c_val_int = 1
                if start > 0: 
                    if config.get('mode') == 'matrix' and row_idx_rule != -1:
                        target_limit_idx = 0
                        for c_limit_idx, limit in enumerate(count_limits):
                            if end <= limit: target_limit_idx = c_limit_idx; break
                            target_limit_idx = c_limit_idx
                        if row_idx_rule < len(matrix_rules) and target_limit_idx < len(matrix_rules[row_idx_rule]):
                            c_val_int = matrix_rules[row_idx_rule][target_limit_idx]
                    elif config.get('mode') == 'count' and row_idx_rule != -1:
                         c_val_int = config['scores_high'][row_idx_rule] if 'scores_high' in config else 1

                coil_str = ""
                if count_in_cell > 0:
                    if start == 0 and end == 0: coil_str = "" 
                    else: coil_str = ",".join(coils_in_cell[:100])

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
        summary_data = [{'Loại': k, 'Số Cuộn': v, 'Tỉ lệ': round(v/total_rolls*100, 2)} for k, v in summary_counts.items()]
        summary_data.sort(key=lambda x: x['Loại'])

        final_result = {
            'summary': summary_data,
            'details': details_list,
            'matrix': matrix_data,
            'col_headers': col_headers,
            'total': total_rolls
        }
        return sanitize_data(final_result)

    except Exception as e:
        print(f"Err Surf {name}: {e}")
        import traceback; traceback.print_exc()
        return default_result
# Tính toán metric dạng Giá Trị (Cơ/Lý/Hóa)
def calculate_metric_value(df, name, config, total_rolls, score_lookup=None):
    """
    Tính Heatmap cho Hình Học/Cơ Lý (Value Mode).
    FIX: Bỏ qua các cuộn thiếu dữ liệu (Score 0) để không vẽ nhầm vào ô Tốt (C1).
    """
    default_result = {'summary': [], 'details': [], 'matrix': [], 'col_headers': [], 'total': 0}
    try:
        # 1. XÁC ĐỊNH LABEL HIỂN THỊ (GIỮ NGUYÊN)
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
        
        # [THÊM BIẾN]: Để theo dõi những cuộn CÓ DỮ LIỆU THỰC SỰ
        valid_data_ids = set() 

        # 4. DUYỆT QUA TỪNG CUỘN (CÓ SỬA ĐỔI)
        for idx, val in col_vals.items():
            coil_id = df.loc[idx, 'CustomerID']
            
            # [SỬA 1]: Mặc định điểm là 0 (Missing) thay vì 1 (Tốt)
            score = 0 
            if score_lookup and coil_id in score_lookup:
                score = score_lookup[coil_id].get(name, 0) # Lấy 0 nếu không tìm thấy

            # [SỬA 2]: Nếu điểm = 0 hoặc giá trị rỗng -> BỎ QUA NGAY (Không tính là Tốt hay Xấu)
            if score == 0 or pd.isna(val):
                continue

            # Nếu code chạy đến đây, nghĩa là cuộn có dữ liệu (Score >= 1)
            valid_data_ids.add(coil_id)

            # Xử lý cuộn Lỗi/Cảnh báo (Score > 1) - Logic cũ giữ nguyên
            if score > 1:
                c_label = f"C{score}" 
                try:
                    if 'scores_value' in config:
                        if score in config['scores_value']:
                            s_idx = config['scores_value'].index(score)
                            c_label = raw_labels[s_idx]
                    else:
                        if (score - 1) < len(raw_labels):
                            c_label = raw_labels[score - 1] # Fix nhẹ index
                except: pass

                val_display = val
                if pd.notnull(val) and isinstance(val, float):
                    val_display = round(val, 4)
                elif pd.isna(val):
                    val_display = "N/A"

                results.append({
                    'Cuộn': coil_id,
                    'Loại': c_label,
                    'RadarScore': score,
                    'Total': 1,
                    'CriticalLabel': c_label,
                    'DetailCounts': {c_label: val_display} 
                })

        # 5. XỬ LÝ DANH SÁCH CUỘN TỐT (CÓ SỬA ĐỔI)
        defect_ids = {r['Cuộn'] for r in results}
        
        # [SỬA 3]: Cuộn Tốt = (Cuộn Có Dữ Liệu) - (Cuộn Lỗi)
        # Thay vì lấy all_ids (bao gồm cả cuộn chưa có KQ), ta chỉ lấy valid_data_ids
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

        # Summary Table (Giữ nguyên)
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
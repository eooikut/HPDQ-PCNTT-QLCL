SINGLE_VAL_HEATMAP = [(1, 1, 'SL')] 
DEFAULT_CONFIG_TEMPLATE = {
    'SAE1006': {
    'MI': {
        'mode': 'matrix', 'group': 'surface', 'target_defect': 'MI',
        # Trục dọc (Y): Kích thước lỗi (mm)
        # Bắt đầu từ -0.1 để hứng giá trị 0
        'bins': [0, 1500, 3000, 4500, 6000, 9000, float('inf')],
        'labels': ['0-1500', '1501-3000', '3001-4500', '4501-6000', '6001-9000', '>9000'],
        
        # Trục ngang (X): Số lượng lỗi
        # Cột 1: 0-10 lỗi | Cột 2: 11-30 | Cột 3: 31-50 | Cột 4: >50
        'count_limits': [10, 30, 50, float('inf')], 

        # Ma trận điểm [Dòng (Size) x Cột (Số lượng)]
        'matrix_rules': [
            [1, 2, 3, 4], # Row: 0-1500 (Ít: C1 -> Nhiều: C4)
            [2, 3, 4, 5], # Row: 1501-3000
            [3, 4, 5, 6], # Row: 3001-4500
            [4, 5, 6, 6], # Row: 4501-6000
            [5, 6, 6, 6], # Row: 6001-9000
            [6, 6, 6, 6]  # Row: >9000 (Luôn nặng)
        ],
        # Config cũ để vẽ Heatmap (vẫn giữ để UI không lỗi, dù logic tính điểm đã dùng matrix)
        'heatmap_cols': [(0,0,'0'),(1,10,'1-10'), (11,30,'11-30'), (31,50,'31-50'), (51,float('inf'),'>50')]
    },
    'EL': {
        'mode': 'matrix', 'group': 'surface', 'target_defect': 'EL',
        # Trục dọc (Y): Kích thước lỗi (mm)
        # Bắt đầu từ -0.1 để hứng giá trị 0
        'bins': [0, 100, 200, 300, 400, 500, float('inf')],
        'labels': ['0-100', '101-200', '201-300', '301-400', '401-500', '>500'],
        
        # Trục ngang (X): Số lượng lỗi
        # Cột 1: 0-10 lỗi | Cột 2: 11-30 | Cột 3: 31-50 | Cột 4: >50
        'count_limits': [10, 30, 50, float('inf')], 

        # Ma trận điểm [Dòng (Size) x Cột (Số lượng)]
        'matrix_rules': [
            [1, 2, 3, 4], # Row: 0-1500 (Ít: C1 -> Nhiều: C4)
            [2, 3, 4, 5], # Row: 1501-3000
            [3, 4, 5, 6], # Row: 3001-4500
            [4, 5, 6, 6], # Row: 4501-6000
            [5, 6, 6, 6], # Row: 6001-9000
            [6, 6, 6, 6]  # Row: >9000 (Luôn nặng)
        ],
        # Config cũ để vẽ Heatmap (vẫn giữ để UI không lỗi, dù logic tính điểm đã dùng matrix)
        'heatmap_cols': [(0,0,'0'), (1,10,'1-10'), (11,30,'11-30'), (31,50,'31-50'), (51,float('inf'),'>50')]
    },
    'LC': {
        'mode': 'matrix', 'group': 'surface', 'target_defect': 'LC',
        # Trục dọc (Y): Kích thước lỗi (mm)
        # Bắt đầu từ -0.1 để hứng giá trị 0
        'bins': [0, 600, 800, 1000, 1200, 1400, float('inf')],
        'labels': ['0-600', '601-800', '801-1000', '1001-1200', '1201-1400', '>1400'],
        
        # Trục ngang (X): Số lượng lỗi
        # Cột 1: 0-10 lỗi | Cột 2: 11-30 | Cột 3: 31-50 | Cột 4: >50
        'count_limits': [15, 25, 50, float('inf')], 

        # Ma trận điểm [Dòng (Size) x Cột (Số lượng)]
        'matrix_rules': [
            [1, 2, 3, 4], # Row: 0-1500 (Ít: C1 -> Nhiều: C4)
            [2, 3, 4, 5], # Row: 1501-3000
            [3, 4, 5, 6], # Row: 3001-4500
            [4, 5, 6, 6], # Row: 4501-6000
            [5, 6, 6, 6], # Row: 6001-9000
            [6, 6, 6, 6]  # Row: >9000 (Luôn nặng)
        ],
        # Config cũ để vẽ Heatmap (vẫn giữ để UI không lỗi, dù logic tính điểm đã dùng matrix)
        'heatmap_cols': [(0,0,'0'),(1,15,'1-15'), (16,25,'16-25'), (26,50,'25-50'), (51,float('inf'),'>50')]
    },
    'SCRT': {
        'mode': 'matrix', 'group': 'surface', 'target_defect': 'SCRT',
        # Trục dọc (Y): Kích thước lỗi (mm)
        # Bắt đầu từ -0.1 để hứng giá trị 0
        'bins': [0, 500, 750, 1000, 1250, 1500, float('inf')],
        'labels': ['0-500', '501-750', '751-1000', '1001-1250', '1251-1500', '>1500'],
        
        # Trục ngang (X): Số lượng lỗi
        # Cột 1: 0-10 lỗi | Cột 2: 11-30 | Cột 3: 31-50 | Cột 4: >50
        'count_limits': [15, 25, 50, float('inf')], 

        # Ma trận điểm [Dòng (Size) x Cột (Số lượng)]
        'matrix_rules': [
            [1, 2, 3, 4], # Row: 0-1500 (Ít: C1 -> Nhiều: C4)
            [2, 3, 4, 5], # Row: 1501-3000
            [3, 4, 5, 6], # Row: 3001-4500
            [4, 5, 6, 6], # Row: 4501-6000
            [5, 6, 6, 6], # Row: 6001-9000
            [6, 6, 6, 6]  # Row: >9000 (Luôn nặng)
        ],
        # Config cũ để vẽ Heatmap (vẫn giữ để UI không lỗi, dù logic tính điểm đã dùng matrix)
        'heatmap_cols': [(0,0,'0'),(1,15,'1-15'), (16,25,'16-25'), (26,50,'25-50'), (51,float('inf'),'>50')]
    },
    'BRUS': {
        'mode': 'matrix', 'group': 'surface', 'target_defect': 'BRUS',
        # Trục dọc (Y): Kích thước lỗi (mm)
        # Bắt đầu từ -0.1 để hứng giá trị 0
        'bins': [0, 100, 200, 300, 400, 500, float('inf')],
        'labels': ['0-100', '101-200', '201-300', '301-400', '401-500', '>500'],
        
        # Trục ngang (X): Số lượng lỗi
        # Cột 1: 0-10 lỗi | Cột 2: 11-30 | Cột 3: 31-50 | Cột 4: >50
        'count_limits': [15, 25, 50, float('inf')], 

        # Ma trận điểm [Dòng (Size) x Cột (Số lượng)]
        'matrix_rules': [
            [1, 2, 3, 4], # Row: 0-1500 (Ít: C1 -> Nhiều: C4)
            [2, 3, 4, 5], # Row: 1501-3000
            [3, 4, 5, 6], # Row: 3001-4500
            [4, 5, 6, 6], # Row: 4501-6000
            [5, 6, 6, 6], # Row: 6001-9000
            [6, 6, 6, 6]  # Row: >9000 (Luôn nặng)
        ],
        # Config cũ để vẽ Heatmap (vẫn giữ để UI không lỗi, dù logic tính điểm đã dùng matrix)
        'heatmap_cols': [(0,0,'0'),(1,15,'1-15'), (16,25,'16-25'), (26,50,'25-50'), (51,float('inf'),'>50')]
    },
    'HPrScale': {
        'mode': 'matrix', 'group': 'surface', 'target_defect': 'HPrScale',
        # Trục dọc (Y): Kích thước lỗi (mm)
        # Bắt đầu từ -0.1 để hứng giá trị 0
         'bins': [0, 1500, 3000, 4500, 6000, 9000, float('inf')],
        'labels': ['0-1500', '1501-3000', '3001-4500', '4501-6000', '6001-9000', '>9000'],
        
        # Trục ngang (X): Số lượng lỗi
        # Cột 1: 0-10 lỗi | Cột 2: 11-30 | Cột 3: 31-50 | Cột 4: >50
        'count_limits': [10, 30, 50, float('inf')], 

        # Ma trận điểm [Dòng (Size) x Cột (Số lượng)]
        'matrix_rules': [
            [1, 2, 3, 4], # Row: 0-1500 (Ít: C1 -> Nhiều: C4)
            [2, 3, 4, 5], # Row: 1501-3000
            [3, 4, 5, 6], # Row: 3001-4500
            [4, 5, 6, 6], # Row: 4501-6000
            [5, 6, 6, 6], # Row: 6001-9000
            [6, 6, 6, 6]  # Row: >9000 (Luôn nặng)
        ],
        # Config cũ để vẽ Heatmap (vẫn giữ để UI không lỗi, dù logic tính điểm đã dùng matrix)
        'heatmap_cols': [(0,0,'0'),(1,10,'1-10'), (11,30,'11-30'), (31,50,'31-50'), (51,float('inf'),'>50')]
    },
    'PRScale': {
        'mode': 'matrix', 'group': 'surface', 'target_defect': 'PRScale',
        # Trục dọc (Y): Kích thước lỗi (mm)
        # Bắt đầu từ -0.1 để hứng giá trị 0
         'bins': [0, 1500, 3000, 4500, 6000, 9000, float('inf')],
        'labels': ['0-1500', '1501-3000', '3001-4500', '4501-6000', '6001-9000', '>9000'],
        
        # Trục ngang (X): Số lượng lỗi
        # Cột 1: 0-10 lỗi | Cột 2: 11-30 | Cột 3: 31-50 | Cột 4: >50
        'count_limits': [10, 30, 50, float('inf')], 

        # Ma trận điểm [Dòng (Size) x Cột (Số lượng)]
        'matrix_rules': [
            [1, 2, 3, 4], # Row: 0-1500 (Ít: C1 -> Nhiều: C4)
            [2, 3, 4, 5], # Row: 1501-3000
            [3, 4, 5, 6], # Row: 3001-4500
            [4, 5, 6, 6], # Row: 4501-6000
            [5, 6, 6, 6], # Row: 6001-9000
            [6, 6, 6, 6]  # Row: >9000 (Luôn nặng)
        ],
        # Config cũ để vẽ Heatmap (vẫn giữ để UI không lỗi, dù logic tính điểm đã dùng matrix)
        'heatmap_cols': [(0,0,'0'), (1,10,'1-10'), (11,30,'11-30'), (31,50,'31-50'), (51,float('inf'),'>50')]
    },
    'RIP': {
        'mode': 'matrix', 'group': 'surface', 'target_defect': 'RIP',
        # Trục dọc (Y): Kích thước
        'bins': [0, 200, 400, 600, 800, 1000, float('inf')], 
        'labels': ['0-200', '201-400', '401-600', '601-800', '801-1000', '>1000'],
        
        # Trục ngang (X): Số lượng lỗi
        # Cột 1: 1 lỗi | Cột 2: 2 lỗi | Cột 3: 3 lỗi | Cột 4: >3 lỗi
        'count_limits': [1, 2, 3, float('inf')], 
        
        # Ma trận điểm
        'matrix_rules': [
            [1, 2, 3, 4], # Row: 0-200 (Size rỗng sẽ rơi vào đây)
            [2, 3, 4, 5], # Row: 201-400
            [3, 4, 5, 6], # Row: 401-600
            [4, 5, 6, 6], # Row: 601-800
            [5, 6, 6, 6], # Row: 801-1000
            [6, 6, 6, 6]  # Row: >1000
        ],
        'heatmap_cols': [(0,0,'0'), (1,1,'1'), (2,2,'2'), (3,3,'3'), (4,float('inf'),'>3')]
    },
    'HOLE': {
        'mode': 'matrix', 'group': 'surface', 'target_defect': 'HOLE',
        # Trục dọc (Y): Kích thước
        'bins': [0, 100, 200, 300, 400, 600, float('inf')],
        'labels': ['0-100', '101-200', '201-300', '301-400', '401-600', '>600'],
        
        # Trục ngang (X): Số lượng lỗi
        # Cột 1: 1 lỗi | Cột 2: 2 lỗi | Cột 3: 3 lỗi | Cột 4: >3 lỗi
        'count_limits': [1, 2, 3, float('inf')], 
        
        # Ma trận điểm
        'matrix_rules': [
            [1, 2, 3, 4], # Row: 0-200 (Size rỗng sẽ rơi vào đây)
            [2, 3, 4, 5], # Row: 201-400
            [3, 4, 5, 6], # Row: 401-600
            [4, 5, 6, 6], # Row: 601-800
            [5, 6, 6, 6], # Row: 801-1000
            [6, 6, 6, 6]  # Row: >1000
        ],
        'heatmap_cols': [(0,0,'0'), (1,1,'1'), (2,2,'2'), (3,3,'3'), (4,float('inf'),'>3')]
    },

        'Flatness': {'mode': 'value', 'group': 'geometry', 'label': 'Độ Phẳng', 'col': 'Flatness [IU]', 'use_abs': True, 'bins': [0, 1, 2, 3, 4, 5, float('inf')], 'labels': ['C1', 'C2', 'C3', 'C4', 'C5', 'C6'], 'scores_value': [1, 2, 3, 4, 5, 6], 'heatmap_cols': SINGLE_VAL_HEATMAP},
        'Crown': {'mode': 'value', 'group': 'geometry', 'label': 'Độ Crown', 'col': 'Crown', 'use_abs': True, 'bins': [0, 40, 50, 60, 70, 80, float('inf')], 'labels': ['C1', 'C2', 'C3', 'C4', 'C5', 'C6'], 'scores_value': [1, 2, 3, 4, 5, 6], 'heatmap_cols': SINGLE_VAL_HEATMAP},
        'Wedge': {'mode': 'value', 'group': 'geometry', 'label': 'Độ Wedge', 'col': 'Wedge', 'use_abs': True, 'bins': [0, 10, 20, 30, 40, 50, float('inf')], 'labels': ['C1', 'C2', 'C3', 'C4', 'C5', 'C6'], 'scores_value': [1, 2, 3, 4, 5, 6], 'heatmap_cols': SINGLE_VAL_HEATMAP},
        'ThickDiff': {'mode': 'value', 'group': 'geometry', 'label': 'Sai lệch dày', 'col': 'Calculated_ThickDiff', 'use_abs': True, 'bins': [0, 0.03, 0.05, 0.10, 0.15, 0.18, float('inf')], 'labels': ['C1', 'C2', 'C3', 'C4', 'C5', 'C6'], 'scores_value': [1, 2, 3, 4, 5, 6], 'heatmap_cols': SINGLE_VAL_HEATMAP},
        
        # WidthDiff: 2 đầu mút là C6 (Xấu nhất), giữa là C1 (Tốt nhất)
        'WidthDiff': {'mode': 'value', 'group': 'geometry', 'label': 'Sai lệch rộng', 'col': 'Calculated_WidthDiff', 'use_abs': True, 
                      'bins': [0, 5, 8, 11, 16, 19, 20, float('inf')], 
                      'labels': ['C6', 'C1', 'C2', 'C3', 'C4', 'C5', 'C6'], 
                      'scores_value': [6, 1, 2, 3, 4, 5, 6], 
                      'heatmap_cols': SINGLE_VAL_HEATMAP},

        # === CƠ LÝ (Properties) - Đổi C0-C5 thành C1-C6 ===
        'YieldPoint': {'mode': 'value', 'group': 'mechanical', 'label': 'GH Chảy', 'col': 'GIỚI HẠN CHẢY', 'bins': [0, 220, 240, 260, 290, 310, float('inf')], 'labels': ['C1', 'C2', 'C3', 'C4', 'C5', 'C6'], 'scores_value': [1, 2, 3, 4, 5, 6], 'heatmap_cols': SINGLE_VAL_HEATMAP},
        'Tensile': {'mode': 'value', 'group': 'mechanical', 'label': 'GH Bền', 'col': 'GIỚI HẠN BỀN', 'bins': [0, 325, 335, 345, 355, 365, float('inf')], 'labels': ['C1', 'C2', 'C3', 'C4', 'C5', 'C6'], 'scores_value': [1, 2, 3, 4, 5, 6], 'heatmap_cols': SINGLE_VAL_HEATMAP},
        'Elongation': {'mode': 'value', 'group': 'mechanical', 'label': 'Độ giãn', 'col': 'ĐỘ GIÃN DÀI', 'bins': [-float('inf'), 30, 35, 40, 45, 50, float('inf')], 'labels': ['C6', 'C5', 'C4', 'C3', 'C2', 'C1'], 'scores_value': [6, 5, 4, 3, 2, 1], 'heatmap_cols': SINGLE_VAL_HEATMAP},
        'Hardness': {'mode': 'value', 'group': 'mechanical', 'label': 'Độ cứng', 'col': 'ĐỘ CỨNG', 'bins': [0, 40, 45, 50, 55, 60, float('inf')], 'labels': ['C1', 'C2', 'C3', 'C4', 'C5', 'C6'], 'scores_value': [1, 2, 3, 4, 5, 6], 'heatmap_cols': SINGLE_VAL_HEATMAP},
        'C': {
        'mode': 'value', 
        'group': 'chemical', 
        'label': 'C', 
        'col': 'C', 
        # Logic: 
        # (0 -> 0.022]: C6 (Quá thấp)
        # (0.022 -> 0.030]: C1 (Chuẩn)
        # (0.030 -> 0.035]: C2
        # ...
        # (0.050 -> inf]: C6 (Quá cao)
        'bins': [0, 0.022, 0.030, 0.035, 0.040, 0.045, 0.050, float('inf')], 
        
        # Nhãn hiển thị tương ứng từng khoảng bin
        'labels': ['C6', 'C1', 'C2', 'C3', 'C4', 'C5', 'C6'], 
        
        # Điểm số tương ứng (Quan trọng để vẽ Radar/Heatmap)
        'scores_value': [6, 1, 2, 3, 4, 5, 6], 
        
        'heatmap_cols': SINGLE_VAL_HEATMAP
    },

    'Mn': {
        'mode': 'value', 
        'group': 'chemical', 
        'label': 'Mn', 
        'col': 'Mn', 
        'bins': [0, 0.150, 0.155, 0.160, 0.170, 0.180, 0.190, float('inf')],
        
        # Nhãn hiển thị
        'labels': ['C6', 'C1', 'C2', 'C3', 'C4', 'C5', 'C6'],
        
        # Điểm số tương ứng
        'scores_value': [6, 1, 2, 3, 4, 5, 6],
        
        'heatmap_cols': SINGLE_VAL_HEATMAP
    },
        'Si': {'mode': 'value', 'group': 'chemical', 'label': 'Si', 'col': 'Si', 'bins': [0, 0.01, 0.015, 0.020, 0.025, 0.03, float('inf')], 'labels': ['C1', 'C2', 'C3', 'C4', 'C5', 'C6'], 'scores_value': [1, 2, 3, 4, 5, 6], 'heatmap_cols': SINGLE_VAL_HEATMAP},
        'P': {'mode': 'value', 'group': 'chemical', 'label': 'P', 'col': 'P', 'bins': [0, 0.005, 0.01, 0.015, 0.019, 0.020, float('inf')], 'labels': ['C1', 'C2', 'C3', 'C4', 'C5', 'C6'], 'scores_value': [1, 2, 3, 4, 5, 6], 'heatmap_cols': SINGLE_VAL_HEATMAP},
        'S': {'mode': 'value', 'group': 'chemical', 'label': 'S', 'col': 'S', 'bins': [0, 0.003, 0.005, 0.0075, 0.010, 0.0125, float('inf')], 'labels': ['C1', 'C2', 'C3', 'C4', 'C5', 'C6'], 'scores_value': [1, 2, 3, 4, 5, 6], 'heatmap_cols': SINGLE_VAL_HEATMAP}
    }
}
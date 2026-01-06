from flask import Blueprint, app, render_template, current_app, request, jsonify
import pandas as pd
import os
import threading
import numpy as np
import json
import math
import db  # Module db.py
import requests
from apscheduler.schedulers.background import BackgroundScheduler
import atexit
from datetime import datetime , timedelta
import time
import requests
import pymysql 
qlcl_bp = Blueprint('qlcl_bp', __name__)
upload_lock = threading.Lock()

# --- 1. CẤU HÌNH MẶC ĐỊNH (TEMPLATE) ---
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
API_GEOMETRY_BATCH_URL = "http://10.192.49.39:5026/hsm" 
# URL lấy lẻ 1 cuộn - Dùng cho Manual Scan
API_GEO_SINGLE_URL = "http://10.192.49.39:5026/hsm?piece_id=" 
# URL Surface
API_SURFACE_URL = "http://10.192.49.39:5025/defects"
VIEW_TPHH = "view_dq1_nmlt_nuocthep" # Thay tên thật vào
VIEW_CO_TINH = "view_dq1_nmhrc1_cotinh"         # Thay tên thật vào
# Cấu hình tên cột trong MySQL (Bạn nhớ sửa lại cho đúng tên thật trong DB của bạn)
COL_ID_CUON = "SampleName"      # Cột ID Cuộn trong View Cơ tính
COL_ID_PHOI_COTINH = "BilletLotName"   # Cột ID Phôi trong View Cơ tính
COL_ID_PHOI_TPHH = "BilletLotCode" 
def rescan_recent_coils_for_mechanical():
    """
    JOB BỔ SUNG: Chạy định kỳ (ví dụ 1 tiếng/lần).
    Mục tiêu: Lấy danh sách các cuộn trong 3 ngày gần đây từ Local DB
    để quét lại MySQL xem đã có Cơ Tính chưa.
    """
    print("\n--- 🐢 BẮT ĐẦU QUÉT BÙ CƠ TÍNH (CATCH-UP JOB) ---")
    
    try:
        conn = db.get_connection()
        # 1. Lấy khoảng 1000 cuộn mới nhất (tương đương sản lượng ~3 ngày)
        # Giả sử bảng coil_data có cột id tự tăng hoặc rowid, hoặc sắp xếp theo coil_id nếu nó có tính thời gian
        # Tốt nhất là thêm cột 'created_at' vào bảng coil_data, nhưng tạm thời lấy theo rowid DESC
        query = "SELECT coil_id FROM coil_data ORDER BY rowid DESC LIMIT 1000"
        rows = conn.execute(query).fetchall()
        conn.close()
        
        if not rows:
            print("💤 Không có dữ liệu cũ để quét lại.")
            return

        # Chuyển thành list ID
        recent_ids = [r['coil_id'] for r in rows]
        
        print(f"🔎 Đang kiểm tra lại {len(recent_ids)} cuộn gần nhất để tìm Cơ tính...")
        
        # 2. Gọi lại hàm sync_properties_mysql với danh sách này
        # Hàm này đã viết ở bước trước, nó có logic "Last Write Wins"
        # nên nếu Cơ tính mới xuất hiện, nó sẽ tự update vào DB.
        updated_count = sync_properties_mysql(target_ids=recent_ids)
        
        print(f"✅ Job Bù đắp hoàn tất. Đã cập nhật thông tin cho {updated_count} cuộn.")

    except Exception as e:
        print(f"❌ Lỗi Job Bù đắp: {str(e)}")
    
    print("--- 🏁 KẾT THÚC QUÉT BÙ ---\n")
# Hàm chính xử lý dữ liệu Geometry từ API và lưu vào DB
def process_and_save_geometry(data_rows):
    """
    Hàm core: Nhận list data từ API Geometry -> Map dữ liệu -> Lưu DB
    [UPDATE]: Ghi đè Raw Data + Bảo vệ điểm số nếu đã chốt tay (is_checked=1)
    """
    processed_ids = []
    batch_data = []
    
    conn = db.get_connection()
    # [SỬA 1]: Lấy thêm cột scores và is_checked
    existing_rows = conn.execute("SELECT coil_id, raw_data, grade, scores, is_checked FROM coil_data").fetchall()
    conn.close()
    
    # [SỬA 2]: Map thêm thông tin scores và is_checked
    existing_map = {r['coil_id']: {
        'raw': json.loads(r['raw_data']) if r['raw_data'] else {}, 
        'grade': r['grade'],
        'scores': json.loads(r['scores']) if r['scores'] else {},
        'is_checked': r['is_checked']
    } for r in existing_rows}

    for row in data_rows:
        if 'debug_printed' not in globals():
            print("\n--- API KEYS DEBUG ---")
            print(row.keys()) # In ra danh sách tên trường
            # print(row)      # Hoặc in cả dòng nếu cần xem giá trị
            print("----------------------\n")
            globals()['debug_printed'] = True
        r_id = row.get('TASK_SLAB') or row.get('piece_id') or row.get('COIL_ID') or row.get('SLAB_ID')
        if not r_id: continue
        coil_id = str(r_id).strip().upper()

        raw_map = {}
        # ... (Phần mapping dữ liệu Crown, Wedge, Flatness giữ nguyên như code cũ) ...
        if row.get('AVG_CROWN') is not None: raw_map['Crown'] = float(row.get('AVG_CROWN'))
        if row.get('AVG_WEDGE') is not None: raw_map['Wedge'] = float(row.get('AVG_WEDGE'))
        if row.get('FLATNEES') is not None: raw_map['Flatness'] = float(row.get('FLATNEES')) 
        
        tgt_thick = pd.to_numeric(row.get('TARGTHK') or row.get('TARGET_THICKNESS'), errors='coerce')
        act_thick = pd.to_numeric(row.get('MEASTHK'), errors='coerce') 
        if pd.notnull(act_thick) and pd.notnull(tgt_thick):
            raw_map['ThickDiff'] = abs(act_thick - tgt_thick)

        # 2. Rộng mục tiêu
        tgt_width = pd.to_numeric(row.get('TARGWIDTH') or row.get('TARGET_WIDTH'), errors='coerce')
        act_width = pd.to_numeric(row.get('MEASWIDTH'), errors='coerce')
        if pd.notnull(act_width) and pd.notnull(tgt_width):
            raw_map['WidthDiff'] = abs(act_width - tgt_width)

        # 3. Khối lượng (Cần check kỹ key của API trả về, thường là WEIGHT, COIL_WEIGHT, hoặc MASS)
        raw_weight = row.get('KhoiLuongPDI') or row.get('COIL_WEIGHT')
        if isinstance(raw_weight, str):
            raw_weight = raw_weight.replace(',', '') # Xóa dấu phẩy
        
        weight_val = pd.to_numeric(raw_weight, errors='coerce')
        
        clean_raw = sanitize_data(raw_map)
        
        # Kiểm tra dữ liệu rỗng
        has_weight = pd.notnull(weight_val) and weight_val > 0
        
        # Chỉ bỏ qua khi: Không có thông số hình học VÀ Không có khối lượng
        if not clean_raw and not has_weight: 
            continue

        # Lấy thông tin hiện tại (hoặc tạo mới)
        # Mặc định is_checked = 0
        current_info = existing_map.get(coil_id, {'raw': {}, 'grade': 'SAE1006', 'scores': {}, 'is_checked': 0})
        
        final_grade = current_info['grade']
        api_grade = str(row.get('STEEL_GRADE', '')).strip().upper()
        if final_grade == 'SAE1006' and api_grade and api_grade not in ['NONE', '', 'NULL']:
            final_grade = api_grade

        # --- LOGIC QUAN TRỌNG: MERGE DATA ---
        full_raw = current_info['raw'].copy()
        full_raw.update(clean_raw) # Ghi đè dữ liệu mới vào
        
        # Tính điểm tự động (luôn tính để tham khảo hoặc dùng nếu chưa chốt)
        new_auto_scores = process_coil_scores(coil_id, full_raw, final_grade)
        
        # --- LOGIC QUAN TRỌNG: QUYẾT ĐỊNH ĐIỂM SỐ ---
        final_scores = new_auto_scores # Mặc định lấy điểm máy
        
        # Nếu đã sửa tay (is_checked == 1) -> Giữ nguyên điểm cũ
        if current_info.get('is_checked') == 1:
            final_scores = current_info['scores']
        batch_data.append({
            'id': coil_id, 
            'grade': final_grade, 
            'raw': full_raw, 
            'scores': final_scores,
            'is_checked': current_info.get('is_checked', 0),
            # [MỚI] Thêm 3 trường này vào dict để lưu
            'weight': float(weight_val) if pd.notnull(weight_val) else 0,
            'target_thick': float(tgt_thick) if pd.notnull(tgt_thick) else 0,
            'target_width': float(tgt_width) if pd.notnull(tgt_width) else 0
        })
        processed_ids.append(coil_id)

    if batch_data:
        # db.save_batch_coils(batch_data)
        db.save_batch_coils_v2(batch_data)
        
    return processed_ids
#sync geometry from external API
def sync_geometry_api():
    """BƯỚC 1: Quét Geometry Batch -> Lưu DB -> Return List IDs"""
    print(f"🔄 [Geometry] Bắt đầu quét lúc {datetime.now().strftime('%H:%M:%S')}...")
    try:
        resp = requests.get(API_GEOMETRY_BATCH_URL, timeout=10)
        json_data = resp.json()
        
        # Xử lý format trả về (List hoặc Dict)
        rows = []
        if isinstance(json_data, list):
            rows = json_data
        elif isinstance(json_data, dict):
            # Tìm key chứa data
            rows = json_data.get('data') or json_data.get('rows') or json_data.get('result') or []
            
        if not rows:
            print("💤 [Geometry] API trả về rỗng.")
            return []

        # Gọi hàm chung để xử lý và lưu
        new_ids = process_and_save_geometry(rows)
        print(f"✅ [Geometry] Đã cập nhật {len(new_ids)} cuộn.")
        return new_ids

    except Exception as e:
        print(f"❌ [Geometry Error] {e}")
        return []
#sync surface defects from external API

def sync_surface_defects(target_ids=None):

    with upload_lock:
        if not target_ids: return 0

        print(f"🔄 [Surface] Bắt đầu quét {len(target_ids)} cuộn...")
        
        conn = db.get_connection()
        placeholders = ','.join('?' * len(target_ids))
        # [SỬA 1]: Lấy thêm scores, is_checked
        query = f"SELECT coil_id, raw_data, grade, scores, is_checked FROM coil_data WHERE coil_id IN ({placeholders})"
        existing_rows = conn.execute(query, target_ids).fetchall()
        conn.close()

        # [SỬA 2]: Map dữ liệu
        existing_map = {r['coil_id']: {
            'raw': json.loads(r['raw_data']) if r['raw_data'] else {}, 
            'grade': r['grade'],
            'scores': json.loads(r['scores']) if r['scores'] else {},
            'is_checked': r['is_checked']
        } for r in existing_rows}

        batch_save = []
        whitelist = DEFAULT_CONFIG_TEMPLATE.get('SAE1006', {}).keys()

        for coil_id in target_ids:
            try:
                # ... (Phần gọi API giữ nguyên) ...
                url = f"{API_SURFACE_URL}?customer_id={coil_id}"
                resp = requests.get(url, timeout=5)
                if resp.status_code != 200: continue
                data = resp.json()
                raw_rows = data.get('rows', [])
                if not raw_rows: continue
    
                coil_defects = {}
                for row in raw_rows:
                    defect = str(row.get('DefectClass')).strip()
                    if defect not in whitelist: continue
                    try: val = float(row.get('Size'))
                    except: val = 0.0
                    if defect not in coil_defects: coil_defects[defect] = []
                    coil_defects[defect].append(val)
                
                # --- LOGIC XỬ LÝ ---
                curr = existing_map.get(coil_id, {'raw': {}, 'grade': 'SAE1006', 'scores': {}, 'is_checked': 0})
                
                final_raw = curr['raw'].copy()
                final_raw.update(coil_defects) # Ghi đè list lỗi mới
                clean_raw = sanitize_data(final_raw)
                
                new_auto_scores = process_coil_scores(coil_id, clean_raw, curr['grade'])
                
                # Bảo vệ điểm
                final_scores = new_auto_scores
                if curr.get('is_checked') == 1:
                    final_scores = curr['scores']
                
                batch_save.append({
                    'id': coil_id, 'grade': curr['grade'], 'raw': clean_raw, 
                    'scores': final_scores, 
                    'is_checked': curr.get('is_checked', 0)
                })
            except: continue

        count_updated = 0
        if batch_save:
            db.save_batch_coils(batch_save)
            count_updated = len(batch_save)
            print(f"✅ [Surface] Đã đồng bộ {count_updated} cuộn.")
            
        return count_updated
    
MYSQL_CONFIG = {
    'host': '10.192.215.11',  # VD: 192.168.1.xxx
    'user': 'viewkcs',
    'password': 'viewkcs@2024',
    'database': 'bkmis_kcshpsdq',
    'port': 3307
}
#sync mechanical & chemical properties from MySQL
def sync_properties_mysql(target_ids=None):
    """
    BƯỚC 3: Đồng bộ Properties (Cơ tính & TPHH)
    [FIXED]: Sửa lỗi tên biến 'cid' -> 'coil_id'
    """
    if not target_ids: return 0

    print(f"🧪 [Properties] Bắt đầu xử lý {len(target_ids)} cuộn...")
    
    ids_str = ",".join([f"'{str(x)}'" for x in target_ids])
    final_data_map = {} 
    slab_to_coils_map = {}

    try:
        conn_mysql = pymysql.connect(**MYSQL_CONFIG, cursorclass=pymysql.cursors.DictCursor)
        
        with conn_mysql.cursor() as cursor:
            # ====================================================
            # GIAI ĐOẠN 1: QUÉT VIEW CƠ TÍNH
            # ====================================================
            sql_cotinh = f"""
                SELECT * FROM {VIEW_CO_TINH} 
                WHERE SUBSTRING_INDEX({COL_ID_CUON}, '/', 1) IN ({ids_str})
            """
            cursor.execute(sql_cotinh)
            rows_cotinh = cursor.fetchall()
            
            target_slabs = set() 

            for r in rows_cotinh:
                # 1.1 Xử lý ID Cuộn
                raw_coil_id = str(r[COL_ID_CUON])
                coil_id = raw_coil_id.split('/')[0].strip().upper() # <--- Tên biến là coil_id
                
                if coil_id not in final_data_map: final_data_map[coil_id] = {}

                # 1.2 Map dữ liệu Cơ Tính [ĐÃ SỬA LỖI TẠI ĐÂY]
                # Thay 'cid' thành 'coil_id'
                if r.get('Yeild') is not None: final_data_map[coil_id]['YieldPoint'] = float(r['Yeild'])
                if r.get('Tensile') is not None: final_data_map[coil_id]['Tensile'] = float(r['Tensile'])
                if r.get('Elongation') is not None: final_data_map[coil_id]['Elongation'] = float(r['Elongation'])
                if r.get('HRB') is not None: final_data_map[coil_id]['Hardness'] = float(r['HRB'])

                # 1.3 Lấy ID Phôi
                slab_id = r.get(COL_ID_PHOI_COTINH)
                if slab_id:
                    slab_id = str(slab_id).strip()
                    target_slabs.add(slab_id)
                    if slab_id not in slab_to_coils_map:
                        slab_to_coils_map[slab_id] = []
                    slab_to_coils_map[slab_id].append(coil_id)

            # ====================================================
            # GIAI ĐOẠN 2: QUÉT VIEW TPHH
            # ====================================================
            if target_slabs:
                slabs_str = ",".join([f"'{str(x)}'" for x in target_slabs])
                
                sql_tphh = f"SELECT * FROM {VIEW_TPHH} WHERE {COL_ID_PHOI_TPHH} IN ({slabs_str})"
                cursor.execute(sql_tphh)
                rows_tphh = cursor.fetchall()

                # LOGIC "GHI ĐÈ" (LAST ROW WINS)
                for r in rows_tphh:
                    slab_id = str(r.get(COL_ID_PHOI_TPHH)).strip()
                    associated_coils = slab_to_coils_map.get(slab_id, [])
                    
                    for coil_id in associated_coils: # <--- Biến vòng lặp là coil_id
                        # [ĐÃ SỬA LỖI TẠI ĐÂY]: Thay 'cid' thành 'coil_id'
                        if r.get('C') is not None: final_data_map[coil_id]['C'] = float(r['C'])
                        if r.get('Mn') is not None: final_data_map[coil_id]['Mn'] = float(r['Mn'])
                        if r.get('Si') is not None: final_data_map[coil_id]['Si'] = float(r['Si'])
                        if r.get('P') is not None: final_data_map[coil_id]['P'] = float(r['P'])
                        if r.get('S') is not None: final_data_map[coil_id]['S'] = float(r['S'])

        conn_mysql.close()
        
        # --- C. LƯU VÀO LOCAL DB ---
        if not final_data_map:
            print("⚠️ [Properties] Không tìm thấy dữ liệu phù hợp trong MySQL.")
            return 0 

        batch_save = []
        conn_local = db.get_connection()
        clean_ids_found = list(final_data_map.keys())
        placeholders = ','.join('?' * len(clean_ids_found))
        
        # [SỬA 1]: Lấy thêm scores, is_checked
        query = f"SELECT coil_id, raw_data, grade, scores, is_checked FROM coil_data WHERE coil_id IN ({placeholders})"
        existing_rows = conn_local.execute(query, clean_ids_found).fetchall()
        conn_local.close()

        # [SỬA 2]: Map dữ liệu
        existing_map = {r['coil_id']: {
            'raw': json.loads(r['raw_data']) if r['raw_data'] else {}, 
            'grade': r['grade'],
            'scores': json.loads(r['scores']) if r['scores'] else {},
            'is_checked': r['is_checked']
        } for r in existing_rows}

        for cid, new_props in final_data_map.items():
            curr = existing_map.get(cid, {'raw': {}, 'grade': 'SAE1006', 'scores': {}, 'is_checked': 0})
            
            final_raw = curr['raw'].copy()
            final_raw.update(new_props) # Ghi đè TPHH/Cơ tính mới
            
            clean_raw = sanitize_data(final_raw)
            new_auto_scores = process_coil_scores(cid, clean_raw, curr['grade'])
            
            # Bảo vệ điểm
            final_scores = new_auto_scores
            if curr.get('is_checked') == 1:
                final_scores = curr['scores']
            
            batch_save.append({
                'id': cid, 
                'grade': curr['grade'], 
                'raw': clean_raw, 
                'scores': final_scores,
                'is_checked': curr.get('is_checked', 0)
            })

        count_updated = 0
        if batch_save:
            db.save_batch_coils(batch_save)
            count_updated = len(batch_save)
            print(f"✅ [Properties] Đã cập nhật xong {count_updated} cuộn.")
            
        return count_updated

    except Exception as e:
        print(f"❌ [Properties Error] {str(e)}")
        # import traceback; traceback.print_exc()
        return 0
# Main sync flow
def run_full_sync_flow():
    """Hàm chạy định kỳ 5 phút: Geo -> Surf -> Prop"""
    print("\n--- 🚀 AUTO SYNC START ---")
    
    # 1. Lấy Geometry -> Trả về list ID mới
    new_ids = sync_geometry_api() 
    
    if new_ids:
        print(f"➡️ Có {len(new_ids)} cuộn mới. Tiếp tục quét Surface & Properties...")
        
        # 2. Lấy Surface theo ID đó
        sync_surface_defects(new_ids) 
        
        # 3. Lấy Properties (MySQL) theo ID đó
        sync_properties_mysql(new_ids)
        
    else:
        print("💤 Không có cuộn mới. Kết thúc chu trình.")
        
    print("--- 🏁 AUTO SYNC END ---\n")
# Scheduler initialization
def init_scheduler():
    if not scheduler.running:
        # JOB 1: REALTIME (Geometry -> Surface -> TPHH)
        # Chạy 5 phút/lần để bắt cuộn mới ra lò
        scheduler.add_job(
            func=run_full_sync_flow, 
            trigger="interval", 
            minutes=5, 
            id='master_sync_job', 
            replace_existing=True,
            next_run_time=datetime.now()
        )
        
        # JOB 2: CATCH-UP (Quét lại Cơ tính) <--- MỚI
        # Chạy 60 phút/lần (1 tiếng)
        # Để cập nhật cơ tính cho các cuộn sinh ra từ 2 ngày trước
        scheduler.add_job(
            func=rescan_recent_coils_for_mechanical, 
            trigger="interval", 
            minutes=60, # Hoặc 30 tùy bạn
            id='mechanical_catchup_job', 
            replace_existing=True,
            # Chạy lần đầu sau 1 phút khởi động để không tranh chấp resource với Job 1 ngay lập tức
            next_run_time=datetime.now() + datetime.timedelta(minutes=1) 
        )
        
        scheduler.start()
@qlcl_bp.route('/api/sync_single_coil', methods=['POST'])
# Manual scan single coil endpoint
def sync_single_coil_endpoint():
    try:
        req = request.json
        coil_id = str(req.get('coil_id', '')).strip()
        if not coil_id: return jsonify({'status': 'error', 'msg': 'Thiếu ID'})
        
        status_report = []

        # --- BƯỚC 1: HÌNH HỌC (Geometry) ---
        geo_found = False
        try:
            # Gọi API lấy data
            resp = requests.get(f"{API_GEO_SINGLE_URL}{coil_id}", timeout=5)
            if resp.status_code == 200:
                data = resp.json()
                rows = []
                if isinstance(data, list): rows = data
                elif isinstance(data, dict): rows = data.get('data') or data.get('rows') or []
                
                if rows:
                    # Gọi hàm lưu và kiểm tra kết quả
                    updated_ids = process_and_save_geometry(rows)
                    if updated_ids: 
                        geo_found = True
        except Exception as e:
            print(f"Geo Err: {e}")

        if geo_found: status_report.append("📐 Geo: ✅")
        else: status_report.append("📐 Geo: ❌")

        # --- BƯỚC 2: BỀ MẶT (Surface) ---
        try:
            # Hàm này giờ trả về số lượng (int)
            count = sync_surface_defects([coil_id])
            if count > 0: status_report.append("🔍 Surf: ✅")
            else: status_report.append("🔍 Surf: ❌ (Không có)")
        except: 
            status_report.append("🔍 Surf: ⚠️ Lỗi")

        # --- BƯỚC 3: CƠ/LÝ/HÓA (Properties) ---
        try:
            # Hàm này giờ trả về số lượng (int)
            count = sync_properties_mysql([coil_id])
            if count > 0: status_report.append("🧪 Prop: ✅")
            else: status_report.append("🧪 Prop: ❌ (Không có)")
        except Exception as e: 
            status_report.append(f"🧪 Prop: ⚠️ Lỗi ({str(e)})")

        # --- TỔNG KẾT ---
        final_msg = f"Kết quả quét {coil_id}: <br/>" + " | ".join(status_report)
        
        return jsonify({'status': 'success', 'msg': final_msg})

    except Exception as e:
        return jsonify({'status': 'error', 'msg': str(e)})
scheduler = BackgroundScheduler()
# Data sanitization function
def sanitize_data(data):
    if isinstance(data, dict):
        return {k: sanitize_data(v) for k, v in data.items()}
    elif isinstance(data, (list, tuple)):
        return [sanitize_data(v) for v in data]
    
    # 1. Xử lý số nguyên Numpy (Nguyên nhân lỗi int64)
    elif isinstance(data, (np.int64, np.int32, np.int16, np.int8, np.integer)):
        return int(data)
    
    # 2. Xử lý số thực Numpy
    elif isinstance(data, (np.float64, np.float32, np.floating)):
        if np.isnan(data): return None
        if np.isinf(data): return "inf"
        return float(data)
    
    # 3. Xử lý số thực Python chuẩn (Nguyên nhân lỗi Infinity)
    elif isinstance(data, float):
        if math.isnan(data): return None
        if math.isinf(data): return "inf" # Chuyển Infinity thành chuỗi "inf"
        return data
    
    # 4. Xử lý Pandas NA
    elif pd.isna(data):
        return None
        
    return data
# Build final response for defect analysis
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

            # [FIX COLOR]: Tính màu dựa trên Score Value cấu hình, không dựa vào Index
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
                
                # Map 1-6 sang 0-5 (để khớp class CSS bg-C0...bg-C5)
                # raw_score 1 (C0) -> c_val 0
                # raw_score 6 (C5) -> c_val 5
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
#   --- 2. QUẢN LÝ CẤU HÌNH ĐIỂM SỐ ---
def desanitize_data(data):
    if isinstance(data, dict): return {k: desanitize_data(v) for k, v in data.items()}
    elif isinstance(data, list): return [desanitize_data(v) for v in data]
    elif data == "inf": return float('inf')
    elif data == "-inf": return float('-inf')
    return data
# Chuẩn hóa CustomerID
def standardize_id(df):
    if 'CustomerID' in df.columns:
        df['CustomerID'] = df['CustomerID'].astype(str).str.replace(r'\.0$', '', regex=True).str.strip().str.upper()
    return df
# Lấy cấu hình điểm số từ DB hoặc mặc định
def get_all_grade_configs():
    cfgs = db.get_config('grade_configs')
    if not cfgs:
        cfgs = desanitize_data(DEFAULT_CONFIG_TEMPLATE)
        db.save_config('grade_configs', sanitize_data(cfgs))
    else:
        cfgs = desanitize_data(cfgs)
    return cfgs
# Tạo cấu trúc menu từ cấu hình điểm số
def get_menu_structure_for_grade(grade_config):
    menu = {'surface': [], 'geometry': [], 'prop': []}
    if not grade_config: return menu
    for name, cfg in grade_config.items():
        grp = cfg.get('group')
        if grp == 'surface': menu['surface'].append(name)
        elif grp == 'geometry': menu['geometry'].append(name)
        elif grp in ['mechanical', 'chemical']: menu['prop'].append(name)
    return menu

# Tính điểm từ giá trị thô và cấu hình
def calculate_score_from_raw(raw_val, config_item):
    try:
        # --- BƯỚC 1: CHUẨN HÓA DỮ LIỆU ĐẦU VÀO ---
        sizes = []
        mode = config_item.get('mode')
        if mode == 'value':
            if raw_val is None or raw_val == '':
                # Nếu không có dữ liệu -> Tùy chọn: return 1 (C1) hoặc return None
                return 1 
            try:
                # Giữ nguyên giá trị thập phân, KHÔNG ép về int
                val = float(raw_val)
                sizes = [val] 
            except:
                return 1
        # TRƯỜNG HỢP B: Mode là COUNT/MATRIX (Đếm số lượng lỗi bề mặt)
        else:
            # 1. Dữ liệu là list (từ file Excel Bề mặt upload)
            if isinstance(raw_val, list):
                for x in raw_val:
                    try:
                        if x is None or x == '': sizes.append(0.0)
                        else: sizes.append(float(x))
                    except: sizes.append(0.0)
            # 2. Dữ liệu None
            elif raw_val is None or raw_val == '':
                return 1 
            # 3. Dữ liệu là số đơn (Tổng số lượng lỗi nhập tay)
            else:
                try:
                    # Ở đây mới dùng int() để lấy số lượng
                    count = int(raw_val) 
                    sizes = [0.0] * count
                except:
                    sizes = []
        if not sizes: return 1 # Không có dữ liệu -> C
        # --- BƯỚC 2: TÍNH ĐIỂM (LOGIC GIỮ NGUYÊN) ---
        # 1. MODE MATRIX
        if mode == 'matrix':
            bins = config_item['bins']
            count_limits = config_item['count_limits']
            matrix = config_item['matrix_rules']
            
            bin_counts = {}
            for s in sizes:
                for i in range(len(bins)-1):
                    # Logic khoảng: (bins[i] < s <= bins[i+1])
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
        # 2. MODE COUNT (Cũ)
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
        # 3. MODE VALUE (Cơ/Lý/Hóa)
        elif mode == 'value':
             # Lấy giá trị thực (đã chuẩn hóa ở Bước 1)
             val = sizes[0]
             
             if config_item.get('use_abs'): val = abs(val)
             
             bins = config_item['bins']
             scores = config_item.get('scores_value', [1,2,3,4,5,6])
             
             # [FIX LOGIC BIÊN]: Dùng < và <= để tránh trùng
             for i in range(len(bins)-1):
                 # Bin đầu tiên: Lấy cả biên dưới
                 if i == 0:
                     if bins[i] <= val <= bins[i+1]:
                         if i < len(scores): return scores[i]
                 else:
                     # Các bin sau: Lớn hơn biên dưới, nhỏ hơn bằng biên trên
                     if bins[i] < val <= bins[i+1]:
                         if i < len(scores): return scores[i]
             return 6 # Ngoài khoảng (thường là quá lớn) -> C6

    except Exception as e:
        print(f"Error calc score: {e}")
        return 1
    return 1
# Xử lý điểm số cho một cuộn dựa trên raw_data và grade
def process_coil_scores(coil_id, raw_data, grade):
    all_configs = get_all_grade_configs()
    grade_config = all_configs.get(grade, all_configs.get('SAE1006'))
    if not grade_config: return {}
    scores = {}
    for key, cfg in grade_config.items():
        val = raw_data.get(key, None)
        scores[key] = calculate_score_from_raw(val, cfg)
    return scores

# Dashboard rendering logic
def render_dashboard_logic(msg=None):
    conn = db.get_connection()
    rows = conn.execute("SELECT * FROM coil_data").fetchall()
    conn.close()
    all_data = {r['coil_id']: {'scores': json.loads(r['scores']) if r['scores'] else {}, 'raw_data': json.loads(r['raw_data']) if r['raw_data'] else {}, 'GRADE': r['grade'], 'IS_CHECKED': r['is_checked']} for r in rows}
    selected_grade = request.args.get('grade', 'SAE1006')
    dashboard_data = regenerate_dashboard_data(all_data, selected_grade)
    
    data_wrapper = {
        'has_data': bool(all_data),
        'time_range': db.get_config('time_range', ''),
        'radar_data': dashboard_data['radar_data'],
        'tabs': dashboard_data['tabs'],
    }
    return render_template('qlcl.html', data=data_wrapper, radar_data=data_wrapper['radar_data'], menu=dashboard_data['menu'], current_grade=selected_grade, msg=msg)
# Regenerate dashboard data based on selected grade
def regenerate_dashboard_data(all_data, selected_grade):
    all_configs = get_all_grade_configs()
    current_config = all_configs.get(selected_grade, all_configs.get('SAE1006'))
    
    final_radar_data = {} # Dữ liệu gửi xuống Frontend (Chứa TOÀN BỘ cuộn)
    target_coils = []     # Dữ liệu để tính toán Tabs thống kê (Chỉ Mác đang chọn)

    # 1. DUYỆT QUA TẤT CẢ CUỘN (Không lọc ngay đầu để tránh mất dữ liệu tìm kiếm)
    for cid, d in all_data.items():
        raw = d.get('raw_data', {})
        current_scores = d.get('scores', {})
        # Lấy grade của cuộn, nếu không có thì mặc định
        coil_grade = d.get('GRADE') if d.get('GRADE') else 'SAE1006'

        # --- A. TÍNH ĐIỂM AUTO (Reference Line) ---
        # Tính điểm máy cho TẤT CẢ các cuộn để hiển thị đúng khi xem chi tiết
        auto_scores = process_coil_scores(cid, raw, coil_grade)

        # --- B. TẠO CẤU TRÚC PHẲNG (FLAT STRUCTURE) ---
        # [QUAN TRỌNG]: Copy điểm số ra lớp ngoài cùng để JS cũ không bị lỗi
        frontend_obj = current_scores.copy() 
        
        # Gắn thêm dữ liệu phụ trợ vào object này
        frontend_obj['auto_scores'] = auto_scores  # <--- Dữ liệu gốc cho Radar mới
        frontend_obj['raw_data'] = raw
        frontend_obj['GRADE'] = coil_grade
        frontend_obj['IS_CHECKED'] = d.get('IS_CHECKED', False)

        # Lưu vào danh sách tổng
        final_radar_data[cid] = frontend_obj

        # --- C. LỌC ĐỂ TÍNH TOÁN TAB (Chỉ tính thống kê cho Mác đang chọn) ---
        if coil_grade == selected_grade:
            target_coils.append({
                'CustomerID': cid, 
                'Raw': raw,
                'Scores': current_scores 
            })
    
    # Nếu không có cuộn nào thuộc Mác này, trả về tabs rỗng nhưng VẪN TRẢ radar_data (để Search vẫn thấy cuộn khác)
    if not target_coils:
        return {
            'tabs': {}, 
            'radar_data': final_radar_data, 
            'menu': get_menu_structure_for_grade(current_config)
        }

    # --- PHẦN TÍNH TOÁN TABS (Giữ nguyên logic cũ) ---
    score_lookup = {item['CustomerID']: item['Scores'] for item in target_coils}

    flattened_data = []
    surface_rows = []
    
    for item in target_coils:
        row_main = {'CustomerID': item['CustomerID']}
        if item['Raw']:
            for k, v in item['Raw'].items():
                row_main[k] = v 
                
                cfg_item = current_config.get(k, {})
                is_surface_mode = cfg_item.get('mode') in ['count', 'matrix']
                is_surface_group = cfg_item.get('group') == 'surface'
                
                if k in current_config and (is_surface_mode or is_surface_group):
                    if isinstance(v, list):
                        for s in v: 
                            surface_rows.append({'CustomerID': item['CustomerID'], 'DefectClass': k, 'Size': s})
                    else:
                        try:
                            val_int = int(v)
                            if val_int > 0:
                                for _ in range(val_int): 
                                    surface_rows.append({'CustomerID': item['CustomerID'], 'DefectClass': k, 'Size': 0})
                        except: pass
                        
        flattened_data.append(row_main)
    
    df_main = pd.DataFrame(flattened_data)
    df_surface = pd.DataFrame(surface_rows) if surface_rows else pd.DataFrame(columns=['CustomerID', 'DefectClass', 'Size'])

    tabs_data = {}
    total_rolls = len(target_coils)
    
    for name, cfg in current_config.items():
        if cfg.get('group') == 'surface':
            tabs_data[name] = calculate_metric_surface(df_surface, name, cfg, total_rolls)
        else:
            tabs_data[name] = calculate_metric_value(df_main, name, cfg, total_rolls, score_lookup)

    return {'tabs': tabs_data, 'radar_data': final_radar_data, 'menu': get_menu_structure_for_grade(current_config)}
# Tính toán metric dạng Bề Mặt
def calculate_metric_surface(df, name, config, total_rolls):
    """
    Heatmap Bề Mặt (FINAL V4 - FULL DETAILS & FIX BUGS):
    1. Heatmap: Dùng logic 'Winner Takes All' (Chỉ xếp vào ô lỗi nặng nhất).
    2. Bảng chi tiết: Hiển thị TOÀN BỘ các lỗi.
    3. Fix lỗi: Đã khai báo default_result.
    """
    # --- [FIX LỖI]: Khai báo default_result ngay đầu hàm để tránh NameError ---
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
    FIX: Map chính xác từ Score (1-6) sang Label cấu hình để hiển thị đúng Matrix.
    """
    default_result = {'summary': [], 'details': [], 'matrix': [], 'col_headers': [], 'total': 0}
    try:
        # 1. XÁC ĐỊNH LABEL HIỂN THỊ
        # Lấy danh sách label từ config để vẽ trục dọc
        raw_labels = config.get('labels', [])
        if not raw_labels: return default_result
        
        display_sizes = []
        seen = set()
        for l in reversed(raw_labels):
            if l not in seen: display_sizes.append(l); seen.add(l)

        # 2. XÁC ĐỊNH LABEL CỦA ĐIỂM 1 (C0/C1 - Tốt nhất)
        # Để dùng cho logic cộng bù cuộn tốt
        target_label_c1 = raw_labels[0] # Mặc định label đầu tiên
        if 'scores_value' in config and 1 in config['scores_value']:
            try:
                # Tìm index của điểm 1 trong cấu hình scores_value
                idx_c1 = config['scores_value'].index(1)
                if idx_c1 < len(raw_labels):
                    target_label_c1 = raw_labels[idx_c1]
            except: pass

        # 3. LẤY GIÁ TRỊ THÔ (Để hiển thị con số chi tiết 0.05, 0.1...)
        col_vals = pd.Series(0, index=df.index)
        if name in df.columns: 
            col_vals = pd.to_numeric(df[name], errors='coerce')
        
        results = []
        
        # 4. DUYỆT QUA TỪNG CUỘN ĐỂ TÍNH TOÁN
        for idx, val in col_vals.items():
            coil_id = df.loc[idx, 'CustomerID']
            
            # --- QUAN TRỌNG: Lấy điểm từ Database (Đồng bộ với Radar) ---
            score = 1 
            if score_lookup and coil_id in score_lookup:
                score = score_lookup[coil_id].get(name, 1)

            # Chỉ xử lý nếu là lỗi (Score > 1) để đưa vào danh sách cảnh báo
            if score > 1:
                # --- FIX: Map từ Score (Số) sang Label (Chuỗi) dựa trên Config ---
                # Ví dụ: Score 6 -> Label 'C6', Score 2 -> Label 'C2'
                c_label = f"C{score}" # Fallback mặc định
                try:
                    # Tìm label tương ứng với điểm số này trong config
                    if 'scores_value' in config:
                        # Dành cho trường hợp WidthDiff (scores không tuần tự 1..6)
                        if score in config['scores_value']:
                            s_idx = config['scores_value'].index(score)
                            c_label = raw_labels[s_idx]
                    else:
                        # Dành cho trường hợp mặc định (i)
                        if (score - 1) < len(raw_labels):
                            c_label = raw_labels[score ]
                except: pass

                # Format giá trị hiển thị
                val_display = val
                if pd.notnull(val) and isinstance(val, float):
                    val_display = round(val, 4)
                elif pd.isna(val):
                    val_display = "N/A"

                results.append({
                    'Cuộn': coil_id,
                    'Loại': c_label,        # Dùng Label thực tế để khớp với Matrix
                    'RadarScore': score,    # Điểm số để tô màu
                    'Total': 1,             # Đánh dấu là có lỗi (để lọt vào range 1-1)
                    'CriticalLabel': c_label,
                    'DetailCounts': {c_label: val_display} 
                })

        # 5. XỬ LÝ DANH SÁCH CUỘN TỐT & CHI TIẾT
        defect_ids = {r['Cuộn'] for r in results}
        all_ids = set(df['CustomerID'].unique())
        non_defect_ids = list(all_ids - defect_ids)
        
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

        # 6. VẼ MATRIX (HEATMAP) - ĐÃ FIX LOGIC SO KHỚP
        matrix_data = []
        col_ranges = config.get('heatmap_cols', [(1, 1, 'SL')])
        col_headers = [r[2] for r in col_ranges]

        for sz in display_sizes: # sz là Label (VD: 'C6', 'C1'...)
            row_obj = {'SizeName': sz, 'Cells': []}
            
            # Lọc dữ liệu theo Label (sz)
            subset = pd.DataFrame()
            if not df_full.empty:
                subset = df_full[df_full['Loại'] == sz]
            
            for start, end, _ in col_ranges:
                cnt = 0
                coils = []
                
                # Logic cộng bù Cuộn Tốt (C1)
                # Nếu Label đang xét (sz) trùng với Label tốt (target_label_c1)
                # VÀ cột đầu tiên (start <= 1)
                is_c1_cell = (sz == target_label_c1 and start <= 1)
                
                if is_c1_cell:
                    # Cộng toàn bộ cuộn không lỗi vào ô này
                    cnt += len(non_defect_ids)
                    coils += non_defect_ids
                
                # Cộng các cuộn Lỗi (nếu có) nằm trong range
                if not subset.empty:
                    in_range = subset[(subset['Total'] >= start) & (subset['Total'] <= end)]
                    cnt += len(in_range)
                    coils += in_range['Cuộn'].astype(str).tolist()

                # TÍNH MÀU (CLASS) DỰA TRÊN ĐIỂM SỐ CẤU HÌNH
                # Thay vì dựa vào index, ta tìm lại điểm số của Label này
                c_val_int = 1 # Mặc định là 1
                try:
                    raw_score = 1
                    if 'scores_value' in config:
                        # Tìm điểm dựa trên label
                        if sz in raw_labels:
                            idx = raw_labels.index(sz)
                            if idx < len(config['scores_value']):
                                raw_score = config['scores_value'][idx]
                    else:
                        # Fallback cũ
                        if sz in raw_labels:
                            raw_score = raw_labels.index(sz) + 1
                    
                    # --- [SỬA TẠI ĐÂY] ---
                    # Nếu CSS của bạn là C1, C2... C6 thì giữ nguyên raw_score
                    c_val_int = raw_score 
                    
                    # CHÚ Ý: Nếu CSS của bạn dùng C0-C5 thì mới dùng dòng dưới (đang comment):
                    # c_val_int = max(0, raw_score - 1) 
                except: pass

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
        import traceback; traceback.print_exc()
        return default_result
# Tính toán metric dạng đơn giản cho 1 biến
def calculate_metric_single(df, name, config, total_rolls):
    default_result = {'summary': [], 'details': [], 'matrix': [], 'col_headers': [], 'total': 0}
    try:
        raw_labels = config['labels']
        display_sizes = []
        seen = set()
        # Reversed để hiện cái quan trọng/lớn nhất lên đầu
        for l in reversed(raw_labels):
            if l not in seen:
                display_sizes.append(l)
                seen.add(l)
        
        # --- PHẦN 1: TÍNH TOÁN ĐIỂM VÀ CHI TIẾT (LOGIC CŨ - GIỮ NGUYÊN) ---
        # (Logic này bạn đã chạy đúng, chỉ copy lại để đảm bảo tính liền mạch)
        
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
                # Lưu CriticalLabel (0-1000...) để vẽ Heatmap Surface
                # Logic tìm CriticalLabel hơi phức tạp, ở đây ta lấy label ứng với điểm cao nhất
                # Tuy nhiên để đơn giản cho hiển thị danh sách, ta lấy c_code
                # Nhưng để vẽ Heatmap, ta cần biết nó thuộc SizeLabel nào
                # Tạm thời ta duyệt lại để lấy SizeLabel chính xác cho Heatmap
                # (Đoạn này đã được xử lý ở loop trên nhưng chưa lưu ra results, ta cần trick nhẹ ở bước vẽ heatmap)
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
            
            # [FIX QUAN TRỌNG TẠI ĐÂY]
            subset = pd.DataFrame()
            if not df_full.empty:
                if config.get('mode') == 'count':
                    # Nếu là Surface: Cần quay lại df_defect gốc để biết cuộn nào có size nằm trong range 'sz'
                    # Vì df_full chỉ chứa kết quả điểm cuối cùng (C1-C6), ko chứa range size
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
# --- ROUTES ---
# Blueprint for Quality Control (QLCL)
@qlcl_bp.route('/qlcl', methods=['GET'])
def qlcl_page():
    return render_dashboard_logic()
# Render trang cấu hình đánh giá chất lượng
@qlcl_bp.route('/config_page', methods=['GET'])
def config_page(): return render_template('config_grade.html')
# Upload Bề Mặt và tính toán điểm
@qlcl_bp.route('/qlcl', methods=['POST'])
def upload_surface():
    """Upload Bề Mặt -> Render Dashboard"""
    with upload_lock:
        file = request.files.get('file')
        if not file: return render_dashboard_logic(msg='Chưa chọn file')
        try:
            df = pd.read_excel(file,sheet_name=0, engine='calamine')
            df.rename(columns={'Cuộn': 'CustomerID', 'Kích thước': 'Size', 'Lỗi': 'DefectClass'}, inplace=True)
            df = standardize_id(df)
            df['Size'] = pd.to_numeric(df['Size'], errors='coerce').fillna(0)

            batch_data = []
            conn = db.get_connection()
            existing_rows = conn.execute("SELECT coil_id, raw_data, grade, scores, is_checked FROM coil_data").fetchall()
            conn.close()
            existing_map = {r['coil_id']: {'raw': json.loads(r['raw_data']) if r['raw_data'] else {}, 'grade': r['grade']} for r in existing_rows}

            grouped = df.groupby('CustomerID')
            for coil_id, group in grouped:
                raw_map = {}
                for defect_type, defect_group in group.groupby('DefectClass'):
                    sizes = defect_group['Size'].tolist()
                    raw_map[defect_type] = sizes 
                
                clean_raw = sanitize_data(raw_map)
                
                current_info = existing_map.get(coil_id, {'raw': {}, 'grade': 'SAE1006'})
                full_raw = current_info['raw'].copy()
                full_raw.update(clean_raw)
                new_auto_scores = process_coil_scores(coil_id, full_raw, current_info['grade'])
                final_scores = new_auto_scores
                if current_info.get('is_checked') == 1:
                    final_scores = current_info['scores'] # Giữ điểm cũ

                batch_data.append({
                    'id': coil_id, 
                    'grade': None, 
                    'raw': clean_raw, 
                    'scores': final_scores,
                    'is_checked': current_info.get('is_checked', 0)
                })

            if batch_data: db.save_batch_coils(batch_data)

            return render_dashboard_logic(msg=f'Upload Bề mặt thành công! Đã xử lý {len(batch_data)} cuộn.')
        except Exception as e: return render_dashboard_logic(msg=f'Lỗi: {str(e)}')
# Upload Hình Học và tính toán điểm
@qlcl_bp.route('/upload_geometry', methods=['POST'])
def upload_geometry():
    """Upload Hình Học: Tính toán từ file Ket_qua_trung_nhau.xlsx"""
    with upload_lock:
        file = request.files.get('file')
        if not file: return jsonify({'msg': 'No file'})
        try:
            # 1. Đọc file (Hỗ trợ cả CSV và Excel)
            try:
                df = pd.read_csv(file) 
            except:
                file.seek(0)
                df = pd.read_excel(file, engine='calamine')

            # Chuẩn hóa tên cột (Viết hoa, xóa khoảng trắng)
            df.columns = (df.columns.astype(str)
                          .str.replace(r'[\n\r]+', ' ', regex=True) # Biến xuống dòng thành dấu cách
                          .str.replace(r'\s+', ' ', regex=True)     # Gộp nhiều dấu cách thành 1
                          .str.strip()
                          .str.upper())
            
            # 2. MAP CỘT THEO YÊU CẦU MỚI (Đã chuẩn hóa thành 1 dòng, viết hoa)
            rename_map = {
                'COIL_ID': 'CustomerID', 'L3 PIECE ID': 'CustomerID',
                'STEEL GRADE': 'Grade_Geo', 'MÃ MÁC THÉP': 'Grade_Geo',
                
                # Cột đo trực tiếp (Giữ nguyên logic cũ)
                'CROWN': 'Crown', 
                'WEDGE': 'Wedge', 
                'FLATNESS': 'Flatness', 'I-UNIT': 'Flatness',

                # --- [MAPPING MỚI CHO CÁC CỘT XUỐNG DÒNG] ---
                # MeasThk\n(mm) -> Sau khi chuẩn hóa sẽ thành "MEASTHK (MM)"
                'MEASTHK (MM)': 'Act_Thick', 
                
                # Targ Thk\n(mm) -> "TARG THK (MM)"
                'TARG THK (MM)': 'Tgt_Thick',
                
                # Meas Width\n(mm) -> "MEAS WIDTH (MM)"
                'MEAS WIDTH (MM)': 'Act_Width',
                
                # Targ Width\n(mm) -> "TARG WIDTH (MM)"
                'TARG WIDTH (MM)': 'Tgt_Width'
            }

            df.rename(columns=rename_map, inplace=True)
            df = standardize_id(df)

            batch_data = []
            conn = db.get_connection()
            existing_rows = conn.execute("SELECT coil_id, raw_data, grade, scores, is_checked FROM coil_data").fetchall()
            conn.close()
            existing_map = {r['coil_id']: {
                'raw': json.loads(r['raw_data']) if r['raw_data'] else {}, 
                'grade': r['grade'],
                'scores': json.loads(r['scores']) if r['scores'] else {},
                'is_checked': r['is_checked']
            } for r in existing_rows}

            count = 0
            for _, row in df.iterrows():
                if 'CustomerID' not in row or pd.isna(row['CustomerID']): continue
                coil_id = str(row['CustomerID']).strip()
                
                # 3. TÍNH TOÁN SAI LỆCH (DIFF)
                
                # ThickDiff = ABS(ACTUAL_THICK_F5 - TARGET_THICK)
                act_thick = pd.to_numeric(row.get('Act_Thick'), errors='coerce')
                tgt_thick = pd.to_numeric(row.get('Tgt_Thick'), errors='coerce')
                thick_diff = 0
                if pd.notnull(act_thick) and pd.notnull(tgt_thick):
                    thick_diff = abs(act_thick - tgt_thick)
                
                # WidthDiff = ABS(MEAS_WIDTH - TARGET_WIDTH)
                act_width = pd.to_numeric(row.get('Act_Width'), errors='coerce')
                tgt_width = pd.to_numeric(row.get('Tgt_Width'), errors='coerce')
                width_diff = 0
                if pd.notnull(act_width) and pd.notnull(tgt_width):
                    width_diff = abs(act_width - tgt_width)

                # 4. TẠO RAW DATA
                raw_map = {}
                
                # Lấy các cột đo trực tiếp nếu có trong file
                for k in ['Flatness', 'Crown', 'Wedge']:
                    if k in row: 
                        val = pd.to_numeric(row[k], errors='coerce')
                        if pd.notnull(val): raw_map[k] = val

                # Lưu thêm giá trị thực (nếu cần hiển thị chi tiết sau này)
                if pd.notnull(act_thick): raw_map['Thickness'] = act_thick
                if pd.notnull(act_width): raw_map['Width'] = act_width

                # Lưu kết quả tính toán vào đúng key Config
                raw_map['ThickDiff'] = thick_diff
                raw_map['WidthDiff'] = width_diff
                val_weight = pd.to_numeric(row.get('KhoiLuongPDI'), errors='coerce') # Cần đảm bảo file Excel có cột WEIGHT
                val_tgt_thick = tgt_thick # Đã lấy ở trên
                val_tgt_width = tgt_width
                clean_raw = sanitize_data(raw_map)

                # 5. Xử lý Mác thép (Ưu tiên giữ nguyên nếu DB đã có, nếu chưa thì lấy từ file này)
                current_info = existing_map.get(coil_id, {'raw': {}, 'grade': 'SAE1006'})
                final_grade = current_info['grade']
                
                excel_grade = str(row.get('Grade_Geo', '')).strip().upper()
                # Nếu trong DB đang là mặc định (SAE1006) mà file này có Grade xịn -> Cập nhật
                if final_grade == 'SAE1006' and excel_grade and excel_grade != 'NAN' and excel_grade != '':
                    final_grade = excel_grade

                # 6. Merge & Tính điểm
                full_raw = current_info['raw'].copy()
                full_raw.update(clean_raw)
                
                new_auto_scores = process_coil_scores(coil_id, full_raw, final_grade)
                
                # --- [SỬA 3]: LOGIC BẢO VỆ ĐIỂM SỐ ---
                final_scores = new_auto_scores
                if current_info.get('is_checked') == 1:
                    final_scores = current_info['scores'] # Giữ nguyên điểm cũ

                batch_data.append({
                    'id': coil_id,
                    'grade': final_grade, 
                    'raw': full_raw, # Lưu full raw đã merge
                    'scores': final_scores,
                    'is_checked': current_info.get('is_checked', 0),
                    'weight': float(val_weight) if pd.notnull(val_weight) else 0,
                    'target_thick': float(val_tgt_thick) if pd.notnull(val_tgt_thick) else 0,
                    'target_width': float(val_tgt_width) if pd.notnull(val_tgt_width) else 0
                })
                count += 1

            if batch_data: db.save_batch_coils_v2(batch_data)
            return jsonify({'msg': f'Upload Hình học OK! Đã cập nhật {count} cuộn.'})
            
        except Exception as e: return jsonify({'msg': str(e)})
# Upload Dữ liệu Cơ Lý Hóa và tính toán điểm        
@qlcl_bp.route('/upload_properties', methods=['POST'])
def upload_properties():
    with upload_lock:
        file = request.files.get('file')
        if not file: return jsonify({'msg': 'No file'})
        try:
            df = None
            # 1. CHIẾN THUẬT ĐỌC FILE MẠNH MẼ
            # Thử đọc là CSV trước
            try:
                df = pd.read_csv(file)
            except:
                file.seek(0)
                try:
                    # Thử đọc CSV với encoding utf-16 (Excel hay lưu dạng này)
                    df = pd.read_csv(file, encoding='utf-16', sep='\t')
                except:
                    file.seek(0)
                    # Cuối cùng thử đọc Excel (Dùng openpyxl cho phổ biến, header=None để tự dò)
                    df = pd.read_excel(file, header=None, engine='openpyxl')

            if df is None: return jsonify({'msg': 'Không thể đọc file. Hãy đảm bảo là file Excel hoặc CSV đúng chuẩn.'})

            # 2. TỰ ĐỘNG TÌM DÒNG TIÊU ĐỀ (HEADER)
            # Quét 10 dòng đầu để tìm dòng chứa chữ "ID" hoặc "Sản phẩm" hoặc "Mã mác thép"
            header_idx = -1
            for i, row in df.head(10).iterrows():
                # Chuyển cả dòng thành chuỗi in hoa để tìm
                row_str = " ".join([str(x).upper() for x in row.values])
                if 'ID' in row_str or 'SAN PHAM' in row_str or 'MA MAC THEP' in row_str:
                    header_idx = i
                    break
            
            # Nếu tìm thấy header thì set lại columns
            if header_idx != -1:
                df.columns = df.iloc[header_idx] # Lấy dòng đó làm tên cột
                df = df.iloc[header_idx+1:].reset_index(drop=True) # Lấy dữ liệu từ dòng sau đó
            
            # Chuẩn hóa tên cột
            df.columns = df.columns.astype(str).str.upper().str.replace('\n', ' ').str.strip()

            # 3. MAPPING CỘT (Bao gồm cả tên trong file CSV mới và Excel cũ)
            rename_map = {
                # Định danh
                'SẢN PHẨM': 'CustomerID', 'SAN PHAM': 'CustomerID', 'ID': 'CustomerID',
                'MÃ MÁC THÉP': 'Grade', 'MA MAC THEP': 'Grade', 'MÁC THÉP': 'Grade',
                
                # Cơ tính
                'G.H CHẢY': 'YieldPoint', 'G.H CHAY': 'YieldPoint', 'GIỚI HẠN CHẢY': 'YieldPoint',
                'G.H BỀN': 'Tensile', 'G.H BEN': 'Tensile', 'GIỚI HẠN BỀN': 'Tensile',
                'ĐỘ GIÃN DÀI': 'Elongation', 'DO GIAN DAI': 'Elongation',
                'ĐỘ CỨNG': 'Hardness', 'DO CUNG': 'Hardness',
                
                # Hóa học
                'C': 'C', 'MN': 'Mn', 'SI': 'Si', 'P': 'P', 'S': 'S'
            }
            df.rename(columns=rename_map, inplace=True)
            df = standardize_id(df)
            
            # --- XỬ LÝ DỮ LIỆU VÀO DB ---
            batch_data = []
            conn = db.get_connection()
            existing_rows = conn.execute("SELECT coil_id, raw_data, grade, scores, is_checked FROM coil_data").fetchall()
            conn.close()
            existing_map = {r['coil_id']: {
                'raw': json.loads(r['raw_data']) if r['raw_data'] else {}, 
                'grade': r['grade'],
                'scores': json.loads(r['scores']) if r['scores'] else {},
                'is_checked': r['is_checked']
            } for r in existing_rows}

            count = 0
            # Các cột cần lấy số liệu
            valid_keys = ['YieldPoint', 'Tensile', 'Elongation', 'Hardness', 'C', 'Mn', 'Si', 'P', 'S']

            for _, row in df.iterrows():
                if 'CustomerID' not in row: continue
                coil_id = str(row['CustomerID']).strip()
                if not coil_id or coil_id.upper() == 'NAN': continue
                
                new_grade = str(row.get('Grade', 'SAE1006')).strip().upper()
                if new_grade in ['NAN', '']: new_grade = 'SAE1006'
                
                raw_map = {}
                for k, v in row.to_dict().items():
                    if k in valid_keys:
                        val_str = str(v).strip().replace(',', '.')
                        try: raw_map[k] = float(val_str)
                        except: raw_map[k] = None
                
                clean_raw = sanitize_data(raw_map)
                
                # Lấy info cũ
                curr = existing_map.get(coil_id, {'raw': {}, 'grade': 'SAE1006', 'scores': {}, 'is_checked': 0})
                
                # Merge Raw Data
                final_raw = curr['raw'].copy()
                final_raw.update(clean_raw)
                
                # Tính điểm tự động
                new_auto_scores = process_coil_scores(coil_id, final_raw, new_grade)
                
                # --- [SỬA 3]: LOGIC BẢO VỆ ĐIỂM SỐ ---
                final_scores = new_auto_scores
                if curr.get('is_checked') == 1:
                    final_scores = curr['scores']
                
                batch_data.append({
                    'id': coil_id,
                    'grade': new_grade,
                    'raw': final_raw, # Lưu Full Raw
                    'scores': final_scores,
                    'is_checked': curr.get('is_checked', 0)
                })
                count += 1

            if batch_data: db.save_batch_coils(batch_data)
            return jsonify({'msg': f'Upload TPHH thành công! Đã cập nhật {count} cuộn.'})
            
        except Exception as e: return jsonify({'msg': f'Lỗi: {str(e)}'})

# API LẤY CẤU HÌNH ĐIỂM SỐ
@qlcl_bp.route('/api/grade_configs', methods=['GET'])
def api_get_configs(): return jsonify(sanitize_data(get_all_grade_configs()))
# API LƯU CẤU HÌNH ĐIỂM SỐ
@qlcl_bp.route('/api/grade_configs', methods=['POST'])
def api_save_configs():
    try:
        new_cfg = desanitize_data(request.json)
        db.save_config('grade_configs', sanitize_data(new_cfg))
        return jsonify({'msg': 'Saved'})
    except Exception as e: return jsonify({'msg': str(e)}), 500
# API ĐẶT LẠI CẤU HÌNH
@qlcl_bp.route('/reset_configs', methods=['POST'])
def reset_configs(): 
    conn = db.get_connection()
    conn.execute("DELETE FROM coil_data")
    conn.commit()
    conn.close()
    return jsonify({'status': 'success'})
# API QUẢN LÝ DANH MỤC DỮ LIỆU
@qlcl_bp.route('/delete_data_category', methods=['POST'])
def delete_data_category(): return jsonify({'status': 'success', 'msg': 'Đã xóa (DB Logic Pending)'})
# API LẤY CẤU HÌNH ĐÁNH GIÁ THỦ CÔNG
@qlcl_bp.route('/get_manual_config', methods=['GET'])
def get_manual_config():
    return jsonify({
        'SURFACE_MANUAL': [{'id': 'oil', 'label': 'Gấp nếp'}, {'id': 'rust', 'label': 'Nếp Nhăn'}, {'id': 'scratch_m', 'label': 'Vết Hằn'}, {'id': 'dirt', 'label': 'Gãy mặt'}, {'id': 'mark', 'label': 'Xỉ thứ cấp'}, {'id': 'scale', 'label': 'Xỉ cán'}, {'id': 'other_s', 'label': 'Xỉ muối tiêu'}],
        'GEO_MANUAL': [{'id': 'telescope', 'label': 'Cong cạnh'}],
        'APPEARANCE': [{'id': 'strap', 'label': 'Khuyết biên'}, {'id': 'label_tag', 'label': 'Bava biên'}, {'id': 'packaging', 'label': 'Vỡ biên'}, {'id': 'edge_cond', 'label': 'Sổ vòng'}, {'id': 'coil_shape', 'label': 'Loa cuộn'}]
    })
# API LƯU ĐIỂM ĐÁNH GIÁ THỦ CÔNG VÀ GHI LOG
@qlcl_bp.route('/save_manual_data', methods=['POST'])
def save_manual_data():
    try:
        req = request.json
        coil_id = req.get('coil_id')
        new_scores = req.get('scores')
        user_name = req.get('user', 'User')

        if not coil_id: return jsonify({'status':'error', 'msg': 'Thiếu ID cuộn'})

        conn = db.get_connection() # <--- Kết nối 1 mở tại đây
        
        try: # Thêm try/finally để chắc chắn đóng conn
            # 1. Lấy dữ liệu CŨ từ DB
            curr_row = conn.execute("SELECT scores FROM coil_data WHERE coil_id=?", (coil_id,)).fetchone()
            old_scores = json.loads(curr_row['scores']) if curr_row and curr_row['scores'] else {}

            # 2. So sánh và chuẩn bị Log
            logs = []
            import datetime
            now = datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")

            for key, new_val in new_scores.items():
                old_val = old_scores.get(key, 0)
                if float(new_val) != float(old_val):
                    logs.append((coil_id, user_name, key, float(old_val), float(new_val), now))

            if logs:
                conn.executemany("INSERT INTO audit_log_qlcl (coil_id, user_name, defect_key, old_value, new_value, changed_at) VALUES (?, ?, ?, ?, ?, ?)", logs)

            

            final_scores = old_scores.copy()
            final_scores.update(new_scores)

            conn.execute(
                "UPDATE coil_data SET scores = ?, is_checked = 1 WHERE coil_id = ?", 
                (json.dumps(final_scores), coil_id)
            )
            
            conn.commit() 
            return jsonify({'status': 'success', 'msg': f'Đã lưu và ghi nhận {len(logs)} thay đổi!'})

        except Exception as e:
            conn.rollback() 
            raise e
        finally:
            conn.close() 

    except Exception as e: 
        return jsonify({'status':'error', 'msg':str(e)})
#  API CẬP NHẬT ĐIỂM LỖI RIÊNG LẺ
@qlcl_bp.route('/update_defect_score', methods=['POST'])
def update_defect_score():
    try:
        req = request.json
        coil_id = req.get('coil_id')
        defect_code = req.get('defect_code')
        score = req.get('score')
        if not coil_id: return jsonify({'status':'error'})
        db.save_coil_scores(coil_id, {defect_code: int(score)})
        conn = db.get_connection()
        conn.execute("UPDATE coil_data SET is_checked=1 WHERE coil_id=?", (coil_id,))
        conn.commit()
        conn.close()
        return jsonify({'status': 'success', 'msg': 'Updated'})
    except Exception as e: return jsonify({'status':'error', 'msg':str(e)})
# --- [API MỚI] CHẠY PHÂN BỔ THEO TIÊU CHUẨN ---
@qlcl_bp.route('/api/run_allocation', methods=['POST'])
def run_allocation():
    try:
        req = request.json
        target_grade = req.get('grade')
        qty_req = int(req.get('qty', 10))
        criteria_list = req.get('criteria', [])
        
        conn = db.get_connection()
        query = "SELECT coil_id, scores FROM coil_data WHERE grade = ? AND (allocated_to IS NULL OR allocated_to = '')"
        rows = conn.execute(query, (target_grade,)).fetchall()
        conn.close()

        candidates = []
        for r in rows:
            if not r['scores']: continue
            scores = json.loads(r['scores'])
            
            total_penalty = 0 
            sort_diffs = []   
            failed_criteria = {} 

            for crit in criteria_list:
                defect_key = crit['defect']
                target_val = int(crit['target'])
                allowed_vals = crit['range']     
                actual_score = scores.get(defect_key, 1)
                
                if actual_score in allowed_vals:
                    diff = 0
                else:
                    # Tính điểm phạt nếu nằm ngoài vùng chấp nhận
                    min_dist = min([abs(actual_score - v) for v in allowed_vals])
                    total_penalty += min_dist
                    diff = min_dist
                    failed_criteria[defect_key] = True
                
                dist_to_target = abs(actual_score - target_val)
                sort_diffs.append(dist_to_target)
            
            # Chỉ lấy các cuộn có độ lệch chấp nhận được (<= 10)
            if total_penalty <= 10: 
                candidates.append({
                    'coil_id': r['coil_id'],
                    'scores': scores,
                    'penalty': total_penalty,       
                    'sort_keys': tuple(sort_diffs), 
                    'failed': failed_criteria       
                })

        # --- LOGIC MỚI: PHÂN LOẠI & LỌC ---
        
        # 1. Tách làm 2 nhóm
        perfect_candidates = [c for c in candidates if c['penalty'] == 0]
        suggestion_candidates = [c for c in candidates if c['penalty'] > 0]
        
        # Sắp xếp nội bộ từng nhóm (Ưu tiên sát target nhất)
        perfect_candidates.sort(key=lambda x: x['sort_keys'])
        suggestion_candidates.sort(key=lambda x: (x['penalty'], x['sort_keys']))
        
        final_list = []
        msg = ""

        # 2. Kiểm tra điều kiện số lượng
        if len(perfect_candidates) >= qty_req:
            # TRƯỜNG HỢP 1: Đủ hàng chuẩn -> Chỉ lấy hàng chuẩn
            # (Trả về toàn bộ hàng chuẩn tìm thấy để user tha hồ chọn)
            final_list = perfect_candidates
            msg = f"✅ Tìm thấy {len(final_list)} cuộn ĐẠT CHUẨN (Đủ yêu cầu)."
        else:
            # TRƯỜNG HỢP 2: Thiếu hàng -> Lấy hết hàng chuẩn + Gợi ý bù vào
            missing = qty_req - len(perfect_candidates)
            # Lấy thêm gợi ý = số còn thiếu + 10 cuộn dư ra để chọn
            limit_suggestions = missing + 10 
            
            top_suggestions = suggestion_candidates[:limit_suggestions]
            final_list = perfect_candidates + top_suggestions
            
            msg = f"⚠️ Chỉ có {len(perfect_candidates)} cuộn chuẩn. Hệ thống gợi ý thêm {len(top_suggestions)} cuộn tiệm cận."

        return jsonify({
            'status': 'success',
            'total_found': len(candidates), # Tổng tìm thấy trong kho
            'perfect_count': len(perfect_candidates),
            'allocated': final_list, # Danh sách trả về frontend đã được lọc
            'msg': msg
        })

    except Exception as e: return jsonify({'status': 'error', 'msg': str(e)})
# API LƯU CẤU HÌNH TDC CHO NHIỀU DÒNG QUY CÁCH
@qlcl_bp.route('/api/save_tdc_batch', methods=['POST'])
def save_tdc_batch():
    try:
        req = request.json
        # 1. Thông tin chung (Master)
        customer = req.get('customer_name', '').strip()
        so_number = req.get('so_number', '').strip()
        grade = req.get('grade', '').strip()
        criteria_json = json.dumps(req.get('criteria', []))
        # 2. Danh sách quy cách (Details)
        items = req.get('items', []) # List các dict {id, thick, width, ...}
        if not customer or not so_number:
            return jsonify({'status': 'error', 'msg': 'Thiếu Tên Khách hoặc Số SO!'})
        conn = db.get_connection()
        count_updated = 0
        count_inserted = 0

        for item in items:
            item_id = item.get('id') # Nếu có ID là update, không là insert
            
            # Lấy dữ liệu từng dòng
            try: thick = float(item.get('thick', 0))
            except: thick = 0
            try: width = float(item.get('width', 0))
            except: width = 0
            try: qty = int(item.get('qty', 0))
            except: qty = 0
            try: total_w = float(item.get('total_weight', 0))
            except: total_w = 0
            try: min_w = float(item.get('min_weight', 0))
            except: min_w = 0
            try: max_w = float(item.get('max_weight', 0))
            except: max_w = 0

            if item_id:
                # UPDATE: Cập nhật quy cách VÀ cập nhật luôn cả tiêu chuẩn (nếu user có sửa ở Master)
                sql = """
                    UPDATE customer_orders 
                    SET customer_name=?, so_number=?, grade=?, criteria_json=?,
                        target_thick=?, target_width=?, qty_req=?, req_weight_total=?,
                        min_weight=?, max_weight=?
                    WHERE id=?
                """
                conn.execute(sql, (customer, so_number, grade, criteria_json, thick, width, qty, total_w, min_w, max_w, item_id))
                count_updated += 1
            else:
                # INSERT: Thêm dòng quy cách mới cho SO này
                sql = """
                    INSERT INTO customer_orders 
                    (customer_name, so_number, grade, criteria_json, target_thick, target_width, qty_req, req_weight_total, min_weight, max_weight)
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """
                conn.execute(sql, (customer, so_number, grade, criteria_json, thick, width, qty, total_w, min_w, max_w))
                count_inserted += 1
        
        conn.commit()
        conn.close()
        
        return jsonify({
            'status': 'success', 
            'msg': f'Đã lưu SO: {so_number}.\nCập nhật: {count_updated} dòng.\nThêm mới: {count_inserted} dòng.'
        })
            
    except Exception as e:
        return jsonify({'status': 'error', 'msg': str(e)})
# API LƯU CẤU HÌNH TDC (1 DÒNG)    
@qlcl_bp.route('/api/save_tdc', methods=['POST'])
def save_tdc_config():
    try:
        req = request.json
        order_id = req.get('id')
        
        # [MỚI] Nhận thêm các tham số quy cách
        thick = float(req.get('thick', 0))
        width = float(req.get('width', 0))
        min_w = float(req.get('min_weight', 0))
        max_w = float(req.get('max_weight', 0))
        total_w_req = float(req.get('req_weight', 0)) # Tổng tấn yêu cầu

        # Cập nhật câu lệnh SQL trong db.py hoặc viết trực tiếp ở đây
        conn = db.get_connection()
        
        criteria_json = json.dumps(req.get('criteria', []))
        
        if order_id:
            # UPDATE
            sql = """
                UPDATE customer_orders 
                SET customer_name=?, grade=?, qty_req=?, criteria_json=?,
                    target_thick=?, target_width=?, min_weight=?, max_weight=?, req_weight_total=?
                WHERE id=?
            """
            params = (req['customer_name'], req['grade'], req['qty'], criteria_json, 
                      thick, width, min_w, max_w, total_w_req, order_id)
        else:
            # INSERT
            sql = """
                INSERT INTO customer_orders 
                (customer_name, grade, qty_req, criteria_json, target_thick, target_width, min_weight, max_weight, req_weight_total)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
            """
            params = (req['customer_name'], req['grade'], req['qty'], criteria_json, 
                      thick, width, min_w, max_w, total_w_req)
            
        conn.execute(sql, params)
        conn.commit()
        conn.close()
        
        return jsonify({'status': 'success', 'msg': 'Đã lưu cấu hình TDC kèm Quy cách!'})
            
    except Exception as e: return jsonify({'status': 'error', 'msg': str(e)})
# API XÓA CẤU HÌNH TDC
@qlcl_bp.route('/api/delete_tdc', methods=['POST'])
def delete_tdc_config():
    try:
        req = request.json
        order_id = req.get('id')
        if not order_id: return jsonify({'status': 'error', 'msg': 'Thiếu ID'})
        
        if db.delete_customer_order(order_id):
            return jsonify({'status': 'success', 'msg': 'Đã xóa TDC thành công'})
        else:
            return jsonify({'status': 'error', 'msg': 'Lỗi khi xóa'})
    except Exception as e: return jsonify({'status': 'error', 'msg': str(e)})
# --- TRANG QUẢN LÝ CHÍNH ---
@qlcl_bp.route('/tdc_manager', methods=['GET'])
def tdc_manager_page():
    """Trang Quản lý cấu hình TDC (Tạo/Sửa/Lưu)"""
    return render_template('tdc_manager.html')
# --- TRANG CHẠY PHÂN BỔ ---
@qlcl_bp.route('/allocation_run', methods=['GET'])
def allocation_run_page():
    """Trang Chạy Phân bổ (Chọn TDC -> Chạy)"""
    return render_template('allocation_run.html')
# HÀM TÌM KIẾM CÁC CUỘN THEO TIÊU CHÍ
def find_candidates(all_rows, criteria_list, exclude_ids):
    """
    Tìm các cuộn thỏa mãn tiêu chí từ danh sách all_rows, 
    loại trừ các cuộn đã bị lấy (exclude_ids)
    """
    candidates = []
    for r in all_rows:
        coil_id = r['coil_id']
        
        # 1. Bỏ qua nếu đã bị TDC trước lấy mất
        if coil_id in exclude_ids: continue
        
        if not r['scores']: continue
        scores = json.loads(r['scores'])
        
        is_valid = True
        sort_keys = [] 
        
        for crit in criteria_list:
            defect_key = crit['defect']
            target_val = int(crit['target'])
            allowed_vals = crit['range']
            
            actual_score = scores.get(defect_key, 1) # Mặc định 1 (C0)
            
            # Check Range
            if actual_score not in allowed_vals:
                is_valid = False
                break
            
            # Tính độ lệch để sort
            diff = abs(actual_score - target_val)
            sort_keys.append(diff)
        
        if is_valid:
            candidates.append({
                'coil_id': coil_id,
                'scores': scores,
                'sort_keys': tuple(sort_keys)
            })
            
    # Sort: Ưu tiên sát Target nhất
    candidates.sort(key=lambda x: x['sort_keys'])
    return candidates
# API CẬP NHẬT SCHEMA CSDL (THÊM CỘT MỚI)
@qlcl_bp.route('/api/update_db_schema', methods=['GET'])
def update_db_schema():
    try:
        conn = db.get_connection()
        msg = []

        # 1. Cập nhật bảng coil_data (Dữ liệu cuộn)
        try: 
            conn.execute("ALTER TABLE coil_data ADD COLUMN allocated_to TEXT")
            msg.append("Đã thêm allocated_to")
        except: pass
        
        try: 
            conn.execute("ALTER TABLE coil_data ADD COLUMN allocated_at TEXT")
            msg.append("Đã thêm allocated_at")
        except: pass

        # 2. Cập nhật bảng customer_orders (Cấu hình Đơn hàng/TDC)
        # [QUAN TRỌNG]: Thêm cột so_number để sửa lỗi "no such column: so_number"
        try: 
            conn.execute("ALTER TABLE customer_orders ADD COLUMN so_number TEXT")
            msg.append("Đã thêm so_number")
        except: pass

        # 3. (Tùy chọn) Thêm các cột quy cách nếu thiếu
        for col in ['target_thick', 'target_width', 'min_weight', 'max_weight', 'req_weight_total']:
            try: 
                conn.execute(f"ALTER TABLE customer_orders ADD COLUMN {col} REAL")
            except: pass
        try: conn.execute("ALTER TABLE coil_data ADD COLUMN allocated_order TEXT")
        except: pass
        conn.commit()
        conn.close()
        
        if not msg: return jsonify({'msg': 'DB đã cập nhật đầy đủ, không cần sửa gì.'})
        return jsonify({'msg': 'Cập nhật thành công: ' + ', '.join(msg)})
        
    except Exception as e: return jsonify({'msg': str(e)})
# API CHẠY PHÂN BỔ THEO NHIỀU DÒNG YÊU CẦU
@qlcl_bp.route('/api/run_batch_allocation', methods=['POST'])
def run_batch_allocation():
    try:
        request_list = request.json 
        conn = db.get_connection()
        
        # 1. Lấy dữ liệu kho (như cũ)
        query = "SELECT coil_id, scores, grade, allocated_to, weight, target_thick, target_width FROM coil_data"
        rows = conn.execute(query).fetchall()
        conn.close()
        
        all_inventory = []
        for r in rows:
            alloc_val = r['allocated_to']
            is_free = (alloc_val is None) or (str(alloc_val).strip() == '')
            if is_free:
                all_inventory.append({
                    'coil_id': r['coil_id'], 
                    'scores': json.loads(r['scores']) if r['scores'] else {}, 
                    'grade': str(r['grade']).strip().upper() if r['grade'] else 'UNKNOWN',
                    'weight': r['weight'] or 0,
                    'thick': r['target_thick'] or 0,
                    'width': r['target_width'] or 0
                })
        
        used_coil_ids = set() 
        final_flat_list = []  

        for req in request_list:
            cust_name = req.get('customer_name', 'Unknown')
            target_grade = str(req.get('grade', '')).strip().upper()
            qty_req = int(req.get('qty', 0))
            criteria = req.get('criteria', [])
            req_thick = float(req.get('thick', 0)) # Dày yêu cầu
            req_width = float(req.get('width', 0)) # Rộng yêu cầu
            grade_inventory = []
            for x in all_inventory:
                if x['coil_id'] in used_coil_ids: continue
                if x['grade'] != target_grade: continue
                
                # Check Quy cách (Nếu request có yêu cầu)
                if req_thick > 0 and abs(x['thick'] - req_thick) > 0.05: continue # Sai lệch dày > 0.05 bỏ
                if req_width > 0 and abs(x['width'] - req_width) > 5: continue 
                req_min_w = float(req.get('min_weight', 0))
                req_max_w = float(req.get('max_weight', 0))
                current_w = x.get('weight', 0)

                # Nếu có yêu cầu Min Weight mà cuộn nhỏ hơn -> Bỏ
                if req_min_w > 0 and current_w < req_min_w: continue
                # Nếu có yêu cầu Max Weight mà cuộn lớn hơn -> Bỏ
                if req_max_w > 0 and current_w > req_max_w: continue   # Sai lệch rộng > 5mm bỏ
                
                grade_inventory.append(x)
            
            candidates = []
            for item in grade_inventory:
                scores = item['scores']
                total_penalty = 0 
                sort_diffs = []   
                failed_criteria = {} 

                for crit in criteria:
                    defect_key = crit['defect']
                    try: target_val = int(crit['target'])
                    except: target_val = 1
                    allowed_vals = crit['range']     
                    actual_score = scores.get(defect_key, 1)
                    
                    if actual_score in allowed_vals:
                        diff = 0
                    else:
                        min_dist = min([abs(actual_score - v) for v in allowed_vals])
                        total_penalty += min_dist
                        diff = min_dist
                        failed_criteria[defect_key] = True
                    sort_diffs.append(abs(actual_score - target_val))

                if total_penalty <= 100: 
                    c_item = item.copy()
                    c_item.update({
                        'penalty': total_penalty,       
                        'sort_keys': tuple(sort_diffs), 
                        'failed': failed_criteria,
                        'customer_alloc': cust_name,
                        # [THÊM DÒNG NÀY]: Trả lại số SO cho frontend hiển thị
                        'order_alloc': req.get('so_number', 'N/A'),
                        'material_desc': f"{req_thick}x{req_width}" # Thêm mô tả quy cách
                    })
                    candidates.append(c_item)

            candidates.sort(key=lambda x: (x['penalty'], x['sort_keys']))

            limit_show = max(qty_req * 3, 50) 

            allocated_view = candidates[:limit_show] 


            temp_take = candidates[:qty_req]
            for item in temp_take:
                used_coil_ids.add(item['coil_id'])

            
            final_flat_list.extend(allocated_view)
            
        return jsonify({
            'status': 'success',
            'allocated': final_flat_list,
            'msg': f"Tìm thấy {len(final_flat_list)} ứng viên tiềm năng."
        })

    except Exception as e:
        return jsonify({'status': 'error', 'msg': str(e)})
# API XÁC NHẬN PHÂN BỔ (CẬP NHẬT VÀO DB)
@qlcl_bp.route('/api/confirm_allocation', methods=['POST'])
def confirm_allocation():
    try:
        req = request.json
        coil_ids = req.get('coil_ids', [])
        tdc_name = req.get('tdc_name')
        so_number = req.get('so_number') # [MỚI] Nhận số SO
        
        if not coil_ids: return jsonify({'status': 'error', 'msg': 'Rỗng'})

        conn = db.get_connection()
        import datetime
        now = datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        # Cập nhật cả allocated_to VÀ allocated_order
        for cid in coil_ids:
        
            conn.execute("""
                UPDATE coil_data 
                SET allocated_to = ?, allocated_order = ?, allocated_at = ? 
                WHERE coil_id = ?
            """, (tdc_name, so_number, now, cid))
            
        conn.commit()
        conn.close()
        return jsonify({'status': 'success', 'msg': 'Đã chốt đơn thành công!'})
    except Exception as e: return jsonify({'status': 'error', 'msg': str(e)})
# --- TRANG LỊCH SỬ PHÂN BỔ ---
@qlcl_bp.route('/allocation_history', methods=['GET'])
def allocation_history_page():
    return render_template('allocation_history.html')
# API LẤY LỊCH SỬ PHÂN BỔ
@qlcl_bp.route('/api/get_order_history', methods=['GET'])
def get_order_history():
    try:
        conn = db.get_connection()
        rows = conn.execute("""
            SELECT * FROM customer_orders 
            ORDER BY customer_name, so_number, created_at DESC
        """).fetchall()
        conn.close()
        
        history = []
        for r in rows:
            history.append({
                'id': r['id'],
                'customer_name': r['customer_name'],
                'so_number': r['so_number'] or 'NO_SO',
                'grade': r['grade'],
                'qty_req': r['qty_req'],
                'criteria': json.loads(r['criteria_json']) if r['criteria_json'] else [],
                'thick': r['target_thick'] or 0,
                'width': r['target_width'] or 0,
                'req_weight': r['req_weight_total'] or 0,
                'min_weight': r['min_weight'],
                'max_weight': r['max_weight']
            })
        return jsonify(history)
    except Exception as e: return jsonify([])
# API LẤY DỮ LIỆU CÁC CUỘN ĐÃ PHÂN BỔ
@qlcl_bp.route('/api/get_allocated_data', methods=['GET'])
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
# API LẤY DANH SÁCH CHỈ TIÊU THEO MÁC THÉP
@qlcl_bp.route('/api/get_grade_criteria', methods=['GET'])
def get_grade_criteria():
    """Trả về danh sách các lỗi/chỉ tiêu của một Mác thép để hiện lên Dropdown"""
    try:
        grade = request.args.get('grade', 'SAE1006')
        all_configs = get_all_grade_configs()
        

        config = all_configs.get(grade, all_configs.get('SAE1006', {}))
        
        criteria_list = []
        
        # Các nhóm hiển thị cho đẹp
        group_names = {
            'surface': '1. Bề mặt',
            'geometry': '2. Hình học',
            'mechanical': '3. Cơ lý',
            'chemical': '4. Hóa học'
        }

        for key, cfg in config.items():

            if key in ['heatmap_cols', 'matrix_rules', 'count_limits', 'bins', 'labels']: 
                continue
            
            # Lấy tên hiển thị (Label)
            label = cfg.get('label', key)
            if cfg.get('target_defect'):
                label = f"{key} ({cfg.get('target_defect')})"
            
            criteria_list.append({
                'code': key,           
                'name': label,       
                'group': group_names.get(cfg.get('group'), 'Khác')
            })

        # Sắp xếp theo nhóm để hiển thị gọn gàng
        criteria_list.sort(key=lambda x: x['group'])
        
        return jsonify(criteria_list)
    except Exception as e:
        return jsonify([])
# API GỠ PHÂN BỔ CHO CÁC CUỘN
@qlcl_bp.route('/api/release_coils', methods=['POST'])
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
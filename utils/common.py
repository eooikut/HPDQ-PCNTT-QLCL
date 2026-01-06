from flask import Blueprint, render_template, request, jsonify
import numpy as np
import pandas as pd
import math
import json

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
def desanitize_data(data):
    if isinstance(data, dict): return {k: desanitize_data(v) for k, v in data.items()}
    elif isinstance(data, list): return [desanitize_data(v) for v in data]
    elif data == "inf": return float('inf')
    elif data == "-inf": return float('-inf')
    return data
def standardize_id(df):
    if 'CustomerID' in df.columns:
        df['CustomerID'] = df['CustomerID'].astype(str).str.replace(r'\.0$', '', regex=True).str.strip().str.upper()
    return df
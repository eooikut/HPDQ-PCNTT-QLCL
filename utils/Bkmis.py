import queue
import threading
import requests
import time
from requests.auth import HTTPBasicAuth

temp_sync_queue = queue.Queue(maxsize=100)
API_TEMP_DEST = "http://10.192.214.23:9001/API/HPDQConnect/TempHRC" # (Nhớ đổi IP)

def push_to_temp_queue(payload_dict):
    """Hàm ném nguyên cục Payload JSON vào hàng đợi"""
    has_valid_data = False
    
    # Duyệt qua tất cả các khóa trong JSON
    for key, val in payload_dict.items():
        if key != "idCuonBo": # Bỏ qua biến ID
            try:
                # Nếu có BẤT KỲ trường nào > 0 thì đánh dấu là hợp lệ và thoát vòng lặp kiểm tra
                if float(val) > 0:
                    has_valid_data = True
                    break
            except ValueError:
                pass
    if not has_valid_data:
        print(f"🚫 [Queue Manager] Từ chối cuộn {payload_dict.get('idCuonBo', 'Unknown')} vì TẤT CẢ 8 trường dữ liệu đều = 0")
        return            
    new_item = {"payload": payload_dict, "retries": 0}
    
    try:
        temp_sync_queue.put_nowait(new_item)
    except queue.Full:
        try:
            oldest_item = temp_sync_queue.get_nowait()
            print(f"🗑️ [Queue Manager] Hộp đầy! Vứt bỏ cuộn cũ: {oldest_item['payload']['idCuonBo']}")
            temp_sync_queue.put_nowait(new_item)
        except queue.Empty:
            pass

def temp_api_worker():
    session = requests.Session()
    session.auth = HTTPBasicAuth("hpdq", "hpdq@2025!")
    
    while True:
        try:
            item = temp_sync_queue.get() 
            payload = item['payload'] # Gói JSON đã chuẩn bị sẵn
            retries = item.get('retries', 0)
            coil_id = payload.get("idCuonBo")
            
            resp = session.post(API_TEMP_DEST, json=payload, timeout=5)
            
            if resp.status_code in [200, 201]:
                res_data = resp.json()
                if res_data.get("success") is True:
                    print(f"✅ [API Shipper] Giao thành công 9 trường dữ liệu cuộn {coil_id}")
                else:
                    print(f"❌ [API Shipper] Đối tác từ chối cuộn {coil_id}: {res_data.get('messages')}")
            else:
                raise Exception(f"HTTP Status Error: {resp.status_code}")

        except Exception as e:
            print(f"⚠️ [API Shipper] Sự cố gửi cuộn {coil_id}: {e}")
            if retries < 3:
                print(f"⏳ Trả cuộn {coil_id} về cuối hàng đợi (Thử lại {retries + 1}/3)")
                item['retries'] = retries + 1
                try:
                    time.sleep(1)
                    temp_sync_queue.put_nowait(item)
                except queue.Full:
                    pass
            else:
                print(f"🗑️ [API Shipper] Đã thử 3 lần không được. Bỏ qua cuộn {coil_id}.")
                try:
                    with open("api_sync_failed_log.txt", "a", encoding="utf-8") as log_file:
                        timestamp = time.strftime('%Y-%m-%d %H:%M:%S')
                        log_file.write(f"[{timestamp}] Lỗi gửi 9 trường API - Cuộn: {coil_id}\n")
                except:
                    pass
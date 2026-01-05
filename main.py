import json
import sys
import os
import time
import random
import gspread
from oauth2client.service_account import ServiceAccountCredentials
from selenium import webdriver
from selenium.webdriver.chrome.options import Options
from selenium.webdriver.chrome.service import Service
from selenium.webdriver.common.by import By
from webdriver_manager.chrome import ChromeDriverManager
from datetime import datetime

# ======================================================
# CẤU HÌNH
# ======================================================
SPREADSHEET_ID = '1YqO4MVEzAz61jc_WCVSS00LpRlrDb5r0LnuzNi6BYUY'
MASTER_SHEET_NAME = 'Sheet1' 

scope = ["https://spreadsheets.google.com/feeds", "https://www.googleapis.com/auth/drive"]

def get_driver():
    """Cấu hình Chrome tối ưu cho Cloud"""
    chrome_options = Options()
    chrome_options.add_argument("--headless")
    chrome_options.add_argument("--no-sandbox")
    chrome_options.add_argument("--disable-dev-shm-usage")
    chrome_options.add_argument("user-agent=Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36")
    
    # Tắt load ảnh để chạy nhanh hơn
    prefs = {"profile.managed_default_content_settings.images": 2}
    chrome_options.add_experimental_option("prefs", prefs)
    
    service = Service(ChromeDriverManager().install())
    return webdriver.Chrome(service=service, options=chrome_options)

def scrape_data(config_path):
    dealer_name = os.path.basename(config_path).replace('.json', '').upper()
    
    with open(config_path, 'r', encoding='utf-8') as f:
        products = json.load(f)

    driver = get_driver()
    results = []
    
    print(f"[{dealer_name}] Bắt đầu quét {len(products)} sản phẩm...")

    for product in products:
        current_time = datetime.now()
        
        # --- CẤU TRÚC DÒNG DỮ LIỆU (7 CỘT) ---
        row = [
            current_time.strftime("%d/%m/%Y"), # 0. Ngày
            current_time.strftime("%H:%M:%S"), # 1. Thời gian
            dealer_name,                       # 2. Đại lý
            product['name'],                   # 3. Tên SP
            "0",                               # 4. Giá (Mặc định 0)
            "Fail",                            # 5. Trạng thái (Mặc định Fail)
            product['url']                     # 6. Link
        ]

        try:
            driver.get(product['url'])
            # time.sleep(1) # Bật lên nếu cần

            selector_type = By.CSS_SELECTOR if product.get('type', 'css') == 'css' else By.XPATH
            price_element = driver.find_element(selector_type, product['selector'])
            
            price_text = price_element.text.strip()
            price_clean = ''.join(filter(str.isdigit, price_text))
            
            if price_clean:
                row[4] = price_clean # Cập nhật giá
                row[5] = "OK"        # Cập nhật trạng thái thành OK
            
            print(f"   -> {product['name']}: {row[5]} - {row[4]}")
            
        except Exception as e:
            # Nếu lỗi thì giữ nguyên là Fail
            # print(f"   Lỗi {product['name']}: {e}") # Bật lên nếu muốn xem chi tiết lỗi
            pass

        results.append(row)

    driver.quit()
    return results

def save_to_master_sheet(data, max_retries=10):
    """Ghi dữ liệu vào Sheet tổng với cơ chế Xếp hàng (Retry)"""
    if not data: return

    creds = ServiceAccountCredentials.from_json_keyfile_name('service_account.json', scope)
    client = gspread.authorize(creds)
    
    for attempt in range(max_retries):
        try:
            sheet = client.open_by_key(SPREADSHEET_ID)
            
            # Cố gắng mở Tab, nếu chưa có thì tạo mới
            try:
                worksheet = sheet.worksheet(MASTER_SHEET_NAME)
            except:
                # Tạo Sheet mới và điền Header
                worksheet = sheet.add_worksheet(title=MASTER_SHEET_NAME, rows=2000, cols=10)
                worksheet.append_row(["Ngày", "Thời gian", "Đại lý", "Sản phẩm", "Giá", "Trạng thái", "Link"])

            # Random thời gian chờ để tránh tắc nghẽn khi 20 con bot cùng ghi
            sleep_time = random.uniform(1, 8)
            time.sleep(sleep_time)

            # Ghi nối tiếp
            worksheet.append_rows(data)
            print(f"✅ Đã ghi thành công {len(data)} dòng vào Sheet tổng!")
            return 

        except Exception as e:
            wait_time = random.uniform(5, 15)
            print(f"⚠️ Sheet đang bận, chờ {wait_time:.1f}s rồi thử lại... (Lỗi: {e})")
            time.sleep(wait_time)
    
    print("❌ THẤT BẠI: Không thể ghi vào Sheet sau nhiều lần thử.")

if __name__ == "__main__":
    if len(sys.argv) < 2:
        print("Vui lòng cung cấp đường dẫn file config")
        sys.exit(1)

    config_file = sys.argv[1]
    
    # 1. Quét
    scraped_data = scrape_data(config_file)
    
    # 2. Lưu
    save_to_master_sheet(scraped_data)

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
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from webdriver_manager.chrome import ChromeDriverManager
from datetime import datetime

# ======================================================
# CẤU HÌNH (BẠN CẦN SỬA MỤC NÀY)
# ======================================================
SPREADSHEET_ID = '1YqO4MVEzAz61jc_WCVSS00LpRlrDb5r0LnuzNi6BYUY' # Thay ID sheet của bạn
MASTER_SHEET_NAME = 'Sheet1' 

scope = ["https://spreadsheets.google.com/feeds", "https://www.googleapis.com/auth/drive"]

def get_driver():
    """Cấu hình Chrome tối ưu và chống phát hiện bot"""
    chrome_options = Options()
    chrome_options.add_argument("--headless=new") 
    chrome_options.add_argument("--no-sandbox")
    chrome_options.add_argument("--disable-dev-shm-usage")
    chrome_options.add_argument("--disable-blink-features=AutomationControlled") 
    chrome_options.add_argument("user-agent=Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36")
    
    # Tắt load ảnh/css để nhẹ máy
    prefs = {
        "profile.managed_default_content_settings.images": 2,
        "profile.managed_default_content_settings.stylesheets": 2,
    }
    chrome_options.add_experimental_option("prefs", prefs)
    chrome_options.add_experimental_option("excludeSwitches", ["enable-automation"])
    
    service = Service(ChromeDriverManager().install())
    return webdriver.Chrome(service=service, options=chrome_options)

def scrape_data(config_path):
    """Hàm cào dữ liệu với logic thử 4 Selector"""
    dealer_name = os.path.basename(config_path).replace('.json', '').upper()
    
    with open(config_path, 'r', encoding='utf-8') as f:
        products = json.load(f)

    driver = get_driver()
    # Timeout 3s: Nếu 1 selector sai thì chỉ đợi 3s rồi chuyển cái khác cho nhanh
    wait = WebDriverWait(driver, 3) 
    results = []
    
    print(f"[{dealer_name}] Bắt đầu quét {len(products)} sản phẩm...")

    for product in products:
        current_time = datetime.now()
        
        # Khởi tạo dòng dữ liệu mặc định là Fail
        row = [
            current_time.strftime("%d/%m/%Y"),
            current_time.strftime("%H:%M:%S"),
            dealer_name,
            product['name'],
            "0",      # Giá
            "Fail",   # Trạng thái
            product['url']
        ]

        try:
            driver.get(product['url'])

            # --- XỬ LÝ ĐA SELECTOR ---
            # 1. Lấy danh sách selectors từ json
            selectors_list = product.get('selectors', [])
            
            # Hỗ trợ tương thích ngược: Nếu json dùng key 'selector' cũ
            if not selectors_list and 'selector' in product:
                selectors_list = [product['selector']]

            is_found = False

            # 2. Vòng lặp thử từng selector (1 -> 2 -> 3 -> 4...)
            for i, sel_str in enumerate(selectors_list):
                try:
                    # Tự động nhận diện XPath hay CSS
                    if str(sel_str).strip().startswith(("/", "(")):
                        by_type = By.XPATH
                    else:
                        by_type = By.CSS_SELECTOR

                    # Chờ element xuất hiện
                    price_element = wait.until(EC.presence_of_element_located((by_type, sel_str)))
                    
                    # Scroll nhẹ để kích hoạt load (cho trang lazy load)
                    driver.execute_script("arguments[0].scrollIntoView({block: 'center'});", price_element)
                    
                    price_text = price_element.text.strip()
                    # Lọc lấy số
                    price_clean = ''.join(filter(str.isdigit, price_text))
                    
                    if price_clean:
                        row[4] = price_clean
                        row[5] = "OK"
                        is_found = True
                        print(f"   ✅ {product['name']}: OK (Selector #{i+1}) - Giá: {price_clean}")
                        break # QUAN TRỌNG: Tìm thấy rồi thì thoát, không thử selector sau nữa
                        
                except Exception:
                    # Nếu lỗi ở selector này, vòng lặp tự động chuyển sang i tiếp theo
                    continue
            
            if not is_found:
                print(f"   ❌ {product['name']}: Fail (Đã thử hết {len(selectors_list)} selectors)")

        except Exception as e:
            print(f"   ☠️ Lỗi tải trang {product['name']}: {str(e)[:50]}")
            pass

        results.append(row)

    driver.quit()
    return results

def save_to_master_sheet(data, max_retries=10):
    """Ghi dữ liệu vào Sheet tổng với cơ chế Xếp hàng (Retry)"""
    if not data: return

    # Cần file service_account.json nằm cùng thư mục
    creds = ServiceAccountCredentials.from_json_keyfile_name('service_account.json', scope)
    client = gspread.authorize(creds)
    
    for attempt in range(max_retries):
        try:
            sheet = client.open_by_key(SPREADSHEET_ID)
            
            try:
                worksheet = sheet.worksheet(MASTER_SHEET_NAME)
            except:
                worksheet = sheet.add_worksheet(title=MASTER_SHEET_NAME, rows=2000, cols=10)
                worksheet.append_row(["Ngày", "Thời gian", "Đại lý", "Sản phẩm", "Giá", "Trạng thái", "Link"])

            # Chờ ngẫu nhiên để tránh xung đột API
            sleep_time = random.uniform(1, 5)
            time.sleep(sleep_time)

            worksheet.append_rows(data)
            print(f"💾 Đã ghi thành công {len(data)} dòng vào Sheet!")
            return 

        except Exception as e:
            wait_time = random.uniform(5, 10)
            print(f"⚠️ Sheet bận, thử lại sau {wait_time:.1f}s... (Lỗi: {e})")
            time.sleep(wait_time)
    
    print("❌ THẤT BẠI: Không thể ghi vào Sheet sau nhiều lần thử.")

if __name__ == "__main__":
    if len(sys.argv) < 2:
        print("Cách dùng: python bot_price.py <ten_file_config.json>")
        sys.exit(1)

    config_file = sys.argv[1]
    
    if not os.path.exists(config_file):
        print(f"❌ Không tìm thấy file: {config_file}")
        sys.exit(1)
        
    scraped_data = scrape_data(config_file)
    save_to_master_sheet(scraped_data)

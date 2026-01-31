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
# CẤU HÌNH
# ======================================================
SPREADSHEET_ID = '1YqO4MVEzAz61jc_WCVSS00LpRlrDb5r0LnuzNi6BYUY'
MASTER_SHEET_NAME = 'Sheet1' 

scope = ["https://spreadsheets.google.com/feeds", "https://www.googleapis.com/auth/drive"]

def get_driver():
    """Cấu hình Chrome tối ưu và chống phát hiện bot"""
    chrome_options = Options()
    # Dùng headless=new (mới nhất) thay vì headless thường để giống người thật hơn
    chrome_options.add_argument("--headless=new") 
    chrome_options.add_argument("--no-sandbox")
    chrome_options.add_argument("--disable-dev-shm-usage")
    chrome_options.add_argument("--disable-blink-features=AutomationControlled") 
    chrome_options.add_argument("user-agent=Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36")
    
    # Tắt load ảnh/css
    prefs = {
        "profile.managed_default_content_settings.images": 2,
        "profile.managed_default_content_settings.stylesheets": 2,
    }
    chrome_options.add_experimental_option("prefs", prefs)
    chrome_options.add_experimental_option("excludeSwitches", ["enable-automation"])
    
    service = Service(ChromeDriverManager().install())
    return webdriver.Chrome(service=service, options=chrome_options)

def scrape_data(config_path):
    dealer_name = os.path.basename(config_path).replace('.json', '').upper()
    
    with open(config_path, 'r', encoding='utf-8') as f:
        products = json.load(f)

    driver = get_driver()
    # Timeout 5s cho mỗi selector (để không đợi quá lâu nếu thử nhiều cái)
    wait = WebDriverWait(driver, 5) 
    results = []
    
    print(f"[{dealer_name}] Bắt đầu quét {len(products)} sản phẩm (Multi-Selector Mode)...")

    for product in products:
        current_time = datetime.now()
        
        row = [
            current_time.strftime("%d/%m/%Y"),
            current_time.strftime("%H:%M:%S"),
            dealer_name,
            product['name'],
            "0",
            "Fail",
            product['url']
        ]

        try:
            driver.get(product['url'])

            # --- XỬ LÝ ĐA SELECTOR ---
            # 1. Lấy danh sách selectors (Ưu tiên key 'selectors', fallback về 'selector' cũ)
            selectors_list = product.get('selectors', [])
            if not selectors_list and 'selector' in product:
                selectors_list = [product['selector']]

            is_found = False

            # 2. Vòng lặp thử từng selector
            for i, sel_str in enumerate(selectors_list):
                try:
                    # Tự động nhận diện XPath hay CSS
                    if str(sel_str).strip().startswith(("/", "(")):
                        by_type = By.XPATH
                    else:
                        by_type = By.CSS_SELECTOR

                    # Chờ element xuất hiện
                    price_element = wait.until(EC.presence_of_element_located((by_type, sel_str)))
                    
                    # Scroll nhẹ để trigger load (quan trọng với trang lazy load)
                    driver.execute_script("arguments[0].scrollIntoView({block: 'center'});", price_element)
                    
                    price_text = price_element.text.strip()
                    price_clean = ''.join(filter(str.isdigit, price_text))
                    
                    if price_clean:
                        row[4] = price_clean
                        row[5] = "OK"
                        is_found = True
                        print(f"   -> {product['name']}: OK (Dùng selector #{i+1}) - {price_clean}")
                        break # Tìm thấy rồi thì thoát vòng lặp ngay, không thử cái sau nữa
                        
                except Exception:
                    # Nếu lỗi selector này, bỏ qua (continue) để thử cái kế tiếp
                    continue
            
            if not is_found:
                print(f"   ⚠️ {product['name']}: Fail (Đã thử hết {len(selectors_list)} selectors)")

        except Exception as e:
            print(f"   ❌ Lỗi Load trang {product['name']}: {str(e)[:50]}")
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
            
            try:
                worksheet = sheet.worksheet(MASTER_SHEET_NAME)
            except:
                worksheet = sheet.add_worksheet(title=MASTER_SHEET_NAME, rows=2000, cols=10)
                worksheet.append_row(["Ngày", "Thời gian", "Đại lý", "Sản phẩm", "Giá", "Trạng thái", "Link"])

            sleep_time = random.uniform(1, 8)
            time.sleep(sleep_time)

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
    
    scraped_data = scrape_data(config_file)
    save_to_master_sheet(scraped_data)

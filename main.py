import json
import sys
import os
import time
import gspread
from oauth2client.service_account import ServiceAccountCredentials
from selenium import webdriver
from selenium.webdriver.chrome.options import Options
from selenium.webdriver.chrome.service import Service
from selenium.webdriver.common.by import By
from webdriver_manager.chrome import ChromeDriverManager
from datetime import datetime

# --- CẤU HÌNH ---
# ID của file Google Sheet (Thay thế bằng ID của bạn)
SPREADSHEET_ID = '1YqO4MVEzAz61jc_WCVSS00LpRlrDb5r0LnuzNi6BYUY'
scope = ["https://spreadsheets.google.com/feeds", "https://www.googleapis.com/auth/drive"]

def get_driver():
    chrome_options = Options()
    chrome_options.add_argument("--headless")  # Chạy ẩn không cần giao diện
    chrome_options.add_argument("--no-sandbox")
    chrome_options.add_argument("--disable-dev-shm-usage")
    # Fake User-Agent để tránh bị chặn
    chrome_options.add_argument("user-agent=Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/90.0.4430.212 Safari/537.36")
    
    service = Service(ChromeDriverManager().install())
    driver = webdriver.Chrome(service=service, options=chrome_options)
    return driver

def scrape_data(config_path):
    # Đọc file config
    with open(config_path, 'r', encoding='utf-8') as f:
        products = json.load(f)

    driver = get_driver()
    results = []
    
    print(f"Bắt đầu quét {len(products)} sản phẩm từ {config_path}...")

    for product in products:
        try:
            driver.get(product['url'])
            # Nghỉ 1 chút để tránh bị chặn (Rate Limit)
            time.sleep(2) 
            
            selector_type = By.CSS_SELECTOR if product.get('type', 'css') == 'css' else By.XPATH
            price_element = driver.find_element(selector_type, product['selector'])
            
            price_text = price_element.text.strip()
            # Lấy số từ chuỗi giá (VD: 20.000.000đ -> 20000000)
            price_clean = ''.join(filter(str.isdigit, price_text))
            
            print(f"Đã lấy: {product['name']} - Giá: {price_clean}")
            
            results.append([
                datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
                product['name'],
                price_clean,
                product['url']
            ])
        except Exception as e:
            print(f"Lỗi sản phẩm {product['name']}: {str(e)}")
            results.append([datetime.now().strftime("%Y-%m-%d"), product['name'], "Lỗi/Hết hàng", product['url']])

    driver.quit()
    return results

def save_to_sheet(sheet_name, data):
    creds = ServiceAccountCredentials.from_json_keyfile_name('service_account.json', scope)
    client = gspread.authorize(creds)
    sheet = client.open_by_key(SPREADSHEET_ID)

    try:
        worksheet = sheet.worksheet(sheet_name)
    except:
        # Nếu chưa có tab đại lý thì tạo mới
        worksheet = sheet.add_worksheet(title=sheet_name, rows=1000, cols=10)
        worksheet.append_row(["Thời gian", "Tên SP", "Giá", "Link"])

    # Ghi dữ liệu nối tiếp vào cuối file
    if data:
        worksheet.append_rows(data)
        print(f"Đã lưu {len(data)} dòng vào tab {sheet_name}")

if __name__ == "__main__":
    # Lấy đường dẫn file config từ tham số dòng lệnh
    if len(sys.argv) < 2:
        print("Vui lòng cung cấp đường dẫn file config")
        sys.exit(1)

    config_file = sys.argv[1] # Ví dụ: configs/tgdd.json
    
    # Lấy tên file làm tên Sheet (VD: tgdd)
    dealer_name = os.path.basename(config_file).replace('.json', '')
    
    data = scrape_data(config_file)
    save_to_sheet(dealer_name, data)

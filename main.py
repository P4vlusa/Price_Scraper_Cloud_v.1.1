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
    """Cấu hình Chrome"""
    chrome_options = Options()
    chrome_options.add_argument("--headless=new") 
    chrome_options.add_argument("--no-sandbox")
    chrome_options.add_argument("--disable-dev-shm-usage")
    chrome_options.add_argument("--disable-blink-features=AutomationControlled") 
    chrome_options.add_argument("user-agent=Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36")
    
    prefs = {"profile.managed_default_content_settings.images": 2, "profile.managed_default_content_settings.stylesheets": 2}
    chrome_options.add_experimental_option("prefs", prefs)
    chrome_options.add_experimental_option("excludeSwitches", ["enable-automation"])
    
    service = Service(ChromeDriverManager().install())
    return webdriver.Chrome(service=service, options=chrome_options)

def scrape_product_logic(driver, wait, product):
    """
    Hàm tìm giá thông minh: Đã nâng cấp từ logic của bạn.
    Thêm 'wait' để xử lý web load chậm.
    """
    selectors_to_try = []

    # 1. Xử lý thông minh file JSON (chấp nhận cả 'selectors' list và 'selector' string)
    # Ưu tiên key 'selectors' (dạng list)
    if 'selectors' in product and isinstance(product['selectors'], list):
        selectors_to_try.extend(product['selectors'])
    
    # Fallback: Key 'selector' (dạng string hoặc list cũ)
    elif 'selector' in product:
        if isinstance(product['selector'], list):
            selectors_to_try.extend(product['selector'])
        else:
            selectors_to_try.append(product['selector'])

    # Nếu không có selector nào
    if not selectors_to_try:
        return "0", "No Selector"

    # 2. Thử từng cái một
    for i, sel in enumerate(selectors_to_try):
        try:
            # Tự động nhận diện XPath/CSS
            sel = str(sel).strip()
            if sel.startswith('/') or sel.startswith('(') or sel.startswith('..'):
                by_type = By.XPATH
            else:
                by_type = By.CSS_SELECTOR
            
            # --- KHÁC BIỆT QUAN TRỌNG: Dùng Wait thay vì find_element ---
            # Chờ tối đa 3 giây cho mỗi selector
            element = wait.until(EC.presence_of_element_located((by_type, sel)))
            
            # Scroll nhẹ để đảm bảo element được render (quan trọng với Shopee/Lazada)
            driver.execute_script("arguments[0].scrollIntoView({block: 'center'});", element)

            raw_text = element.text
            # Lọc lấy số (Logic của bạn)
            clean_price = ''.join(filter(str.isdigit, raw_text))
            
            # Kiểm tra giá trị hợp lệ
            if clean_price and int(clean_price) > 0:
                print(f"   ✅ OK tại selector #{i+1}: {clean_price}")
                return clean_price, "OK"
                
        except Exception:
            # Thử cái tiếp theo
            continue
            
    # Thử hết mà vẫn trượt
    return "0", "Fail"

def scrape_data(config_path):
    dealer_name = os.path.basename(config_path).replace('.json', '').upper()
    with open(config_path, 'r', encoding='utf-8') as f:
        products = json.load(f)

    driver = get_driver()
    # Tạo biến wait dùng chung, timeout 3s mỗi lần thử
    wait = WebDriverWait(driver, 3) 
    results = []
    
    print(f"[{dealer_name}] Bắt đầu quét {len(products)} sản phẩm...")

    for product in products:
        current_time = datetime.now()
        
        # Gọi hàm logic riêng đã tách ra
        try:
            driver.get(product['url'])
            price, status = scrape_product_logic(driver, wait, product)
        except Exception as e:
            print(f"   ☠️ Lỗi tải trang: {str(e)[:50]}")
            price, status = "0", "ErrLoad"

        # Nếu Fail, in ra để debug
        if status == "Fail":
            print(f"   ❌ {product['name']}: Không tìm thấy giá (Đã thử hết selector)")

        row = [
            current_time.strftime("%d/%m/%Y"),
            current_time.strftime("%H:%M:%S"),
            dealer_name,
            product['name'],
            price,
            status,
            product['url']
        ]
        results.append(row)

    driver.quit()
    return results

def save_to_master_sheet(data, max_retries=10):
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

            time.sleep(random.uniform(1, 3))
            worksheet.append_rows(data)
            print(f"💾 Đã ghi {len(data)} dòng vào Sheet!")
            return 
        except Exception as e:
            time.sleep(5)
    print("❌ Lỗi ghi Sheet.")

if __name__ == "__main__":
    if len(sys.argv) < 2:
        print("Cách dùng: python bot.py <config.json>")
        sys.exit(1)
    scrape_data(sys.argv[1])
    save_to_master_sheet(scrape_data(sys.argv[1]))

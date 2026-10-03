import time
import os
import sys
sys.path.insert(0, ".")

from selenium import webdriver
from selenium.webdriver.chrome.options import Options
from selenium.webdriver.common.by import By

from app.db import get_user_by_email, get_user_display
from app.auth import create_access_token

user = get_user_by_email("manual_demo@budgettracker.local")
token = create_access_token(user["id"], user["email"])
user_display = get_user_display(user["id"])

opts = Options()
opts.add_argument('--headless=new')
opts.add_argument('--window-size=375,812')
opts.add_argument('--disable-gpu')
opts.add_argument('--no-sandbox')
opts.add_argument('--disable-service-workers')
opts.set_capability('goog:loggingPrefs', {'browser': 'ALL'})

driver = webdriver.Chrome(options=opts)
try:
    print("1. Opening app...")
    driver.get('http://127.0.0.1:8000')
    time.sleep(1)

    print("2. Injecting auth session...")
    driver.execute_script("""
        sessionStorage.setItem('abt_token', arguments[0]);
        sessionStorage.setItem('abt_user', JSON.stringify(arguments[1]));
        sessionStorage.setItem('abt_onboarding_skipped', '1');
        location.reload();
    """, token, user_display)
    time.sleep(2)

    print("3. Switching to transactions...")
    driver.execute_script("window.switchView('transactions');")

    for i in range(12):
        time.sleep(1)
        loader_disp = driver.find_element(By.ID, "tx-loader").value_of_css_property("display")
        rows = driver.find_elements(By.CLASS_NAME, "btn-edit-tx")
        print(f"t={i+1}s: loader={loader_disp}, edit_btns={len(rows)}")
        if len(rows) > 0:
            print("Transactions table loaded successfully!")
            break

    for l in driver.get_log('browser'):
        print(f"LOG: [{l['level']}] {l['message']}")

finally:
    driver.quit()

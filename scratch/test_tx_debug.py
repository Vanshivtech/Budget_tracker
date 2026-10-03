import time
import os
import sys
sys.path.insert(0, ".")

from selenium import webdriver
from selenium.webdriver.chrome.options import Options
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC

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
opts.set_capability('goog:loggingPrefs', {'browser': 'ALL'})

driver = webdriver.Chrome(options=opts)
try:
    print("1. Opening app...")
    driver.get('http://127.0.0.1:8000')
    time.sleep(1)

    print("2. Injecting auth...")
    driver.execute_script("""
        sessionStorage.setItem('abt_token', arguments[0]);
        sessionStorage.setItem('abt_user', JSON.stringify(arguments[1]));
        sessionStorage.setItem('abt_onboarding_skipped', '1');
        location.reload();
    """, token, user_display)
    time.sleep(2)

    print("3. Switching to transactions view...")
    driver.execute_script("window.switchView('transactions');")
    time.sleep(15)

    loader = driver.find_element(By.ID, "tx-loader")
    print("tx-loader display:", loader.value_of_css_property("display"))
    
    table_card = driver.find_element(By.ID, "tx-table-container")
    print("tx-table-container innerHTML length:", len(table_card.get_attribute("innerHTML")))
    print("tx-table-container text snippet:", table_card.text[:200])

    logs = driver.get_log('browser')
    print(f"Browser logs ({len(logs)} entries):")
    for entry in logs:
        print(f"[{entry['level']}] {entry['message']}")

finally:
    driver.quit()

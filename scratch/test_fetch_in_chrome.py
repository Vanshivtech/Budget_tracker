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
opts.set_capability('goog:loggingPrefs', {'browser': 'ALL'})

driver = webdriver.Chrome(options=opts)
try:
    driver.get('http://127.0.0.1:8000')
    time.sleep(1)

    driver.execute_script("""
        sessionStorage.setItem('abt_token', arguments[0]);
        sessionStorage.setItem('abt_user', JSON.stringify(arguments[1]));
        sessionStorage.setItem('abt_onboarding_skipped', '1');
        location.reload();
    """, token, user_display)
    time.sleep(2)

    res = driver.execute_async_script("""
        const done = arguments[arguments.length - 1];
        fetch('/api/transactions?limit=10', {
            headers: {
                'Authorization': 'Bearer ' + sessionStorage.getItem('abt_token'),
                'Content-Type': 'application/json'
            }
        })
        .then(r => r.json().then(data => done({ status: r.status, ok: r.ok, data })))
        .catch(err => done({ error: err.toString() }));
    """)
    print("Fetch result from browser:", res)

    # Now let's try calling window.loadTransactionsView() or switchView('transactions')
    driver.execute_script("window.switchView('transactions');")
    for i in range(10):
        time.sleep(1)
        loader_disp = driver.find_element(By.ID, "tx-loader").value_of_css_property("display")
        container_html = driver.find_element(By.ID, "tx-table-container").get_attribute("innerHTML")
        print(f"t={i+1}s: loader_disp={loader_disp}, html_len={len(container_html)}")
        if loader_disp == "none":
            break

    for l in driver.get_log('browser'):
        print(f"BROWSER LOG: [{l['level']}] {l['message']}")

finally:
    driver.quit()

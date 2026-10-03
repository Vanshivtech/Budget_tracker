"""
Automated capture of all 5 required mobile screenshots (375px viewport width)
for manual entry and management features.
"""
import time
import os
import sys
sys.path.insert(0, ".")

from selenium import webdriver
from selenium.webdriver.chrome.options import Options
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait, Select
from selenium.webdriver.support import expected_conditions as EC

from app.db import get_user_by_email, get_user_display
from app.auth import create_access_token

OUT_DIR = os.path.abspath("scratch/screenshots")
os.makedirs(OUT_DIR, exist_ok=True)

user = get_user_by_email("manual_demo@budgettracker.local")
token = create_access_token(user["id"], user["email"])
user_display = get_user_display(user["id"])

opts = Options()
opts.add_argument('--headless=new')
opts.add_argument('--window-size=375,812')
opts.add_argument('--disable-gpu')
opts.add_argument('--no-sandbox')
driver = webdriver.Chrome(options=opts)
driver.set_window_size(375, 812)

try:
    print("1. Loading app...")
    driver.get('http://127.0.0.1:8000')
    time.sleep(1)
    
    print("2. Setting authenticated session...")
    driver.execute_script("window.setAuthSession(arguments[0], arguments[1]);", token, user_display)
    time.sleep(1)

    # -------------------------------------------------------------
    # 1. Quick-Add Bar Mobile
    # -------------------------------------------------------------
    print("3. Capturing Screen 1: Quick-Add Bar on Dashboard...")
    driver.execute_script("window.switchView('dashboard');")
    time.sleep(2)
    
    amt = WebDriverWait(driver, 15).until(
        EC.presence_of_element_located((By.ID, "dashboard-quick-add-wrap-amt"))
    )
    amt.clear()
    amt.send_keys("250")
    note = driver.find_element(By.ID, "dashboard-quick-add-wrap-note")
    note.clear()
    note.send_keys("Coffee & team snacks")
    tag = driver.find_element(By.ID, "dashboard-quick-add-wrap-tag")
    tag.clear()
    tag.send_keys("office")
    
    driver.execute_script("window.scrollTo(0, 0);")
    time.sleep(0.5)
    p1 = os.path.join(OUT_DIR, "01_quick_add_bar_mobile.png")
    driver.save_screenshot(p1)
    print("   Saved:", p1, f"({os.path.getsize(p1)} bytes)")

    # -------------------------------------------------------------
    # 2. Transaction List View & Edit Modal
    # -------------------------------------------------------------
    print("4. Capturing Screen 2: Transaction List & Edit Modal...")
    driver.execute_script("window.switchView('transactions');")
    time.sleep(2)
    for l in driver.get_log('browser'):
        print("BROWSER LOG AFTER SWITCH:", l)
    
    try:
        WebDriverWait(driver, 20).until(
            lambda d: d.find_element(By.ID, "tx-loader").value_of_css_property("display") == "none"
        )
    except Exception as e:
        print("WAIT TIMEOUT EXCEPTION:", e)
        for l in driver.get_log('browser'):
            print("BROWSER LOG ON TIMEOUT:", l)
        thtml = driver.execute_script("return document.getElementById('tx-table-container').innerHTML;")
        print("TABLE HTML ON TIMEOUT:", thtml)
        raise e
    time.sleep(0.5)
    
    edit_btns = driver.find_elements(By.CLASS_NAME, "btn-edit-tx")
    print(f"   Found {len(edit_btns)} edit buttons")
    if edit_btns:
        driver.execute_script("arguments[0].scrollIntoView({block: 'center'});", edit_btns[0])
        time.sleep(0.3)
        driver.execute_script("arguments[0].click();", edit_btns[0])
        
        WebDriverWait(driver, 10).until(
            EC.visibility_of_element_located((By.ID, "modal-expense-entry"))
        )
        time.sleep(0.5)
        p2 = os.path.join(OUT_DIR, "02_transactions_view_and_edit_modal_mobile.png")
        driver.save_screenshot(p2)
        print("   Saved:", p2, f"({os.path.getsize(p2)} bytes)")
        
        close_btn = driver.find_element(By.ID, "expense-modal-close")
        driver.execute_script("arguments[0].click();", close_btn)
        time.sleep(0.5)

    # -------------------------------------------------------------
    # 3. Budget Manager in Settings
    # -------------------------------------------------------------
    print("5. Capturing Screen 3: Budget Manager in Settings...")
    driver.execute_script("window.switchView('settings');")
    time.sleep(2)
    
    card_bm = WebDriverWait(driver, 15).until(
        EC.presence_of_element_located((By.ID, "settings-budget-manager-card"))
    )
    driver.execute_script("arguments[0].scrollIntoView({block: 'start'});", card_bm)
    time.sleep(1)
    p3 = os.path.join(OUT_DIR, "03_budget_manager_mobile.png")
    driver.save_screenshot(p3)
    print("   Saved:", p3, f"({os.path.getsize(p3)} bytes)")

    # -------------------------------------------------------------
    # 4. Udhar Add Form with Repayment Warning
    # -------------------------------------------------------------
    print("6. Capturing Screen 4: Udhar Add Form with Repayment Warning...")
    driver.execute_script("window.switchView('udhar');")
    time.sleep(2)
    
    btn_add_u = WebDriverWait(driver, 15).until(
        EC.presence_of_element_located((By.ID, "btn-add-udhar-manual"))
    )
    driver.execute_script("arguments[0].click();", btn_add_u)
    
    WebDriverWait(driver, 15).until(
        EC.visibility_of_element_located((By.ID, "modal-udhar-entry"))
    )
    time.sleep(0.5)

    kind_sel = Select(driver.find_element(By.ID, "udhar-entry-kind"))
    kind_sel.select_by_value("received_back")
    driver.execute_script("document.getElementById('udhar-entry-kind').dispatchEvent(new Event('change'));")
    
    p_in = driver.find_element(By.ID, "udhar-person-input")
    p_in.clear()
    p_in.send_keys("Rahul Sharma")
    a_in = driver.find_element(By.ID, "udhar-amount-input")
    a_in.clear()
    a_in.send_keys("3500")

    driver.execute_script("document.getElementById('udhar-person-input').dispatchEvent(new Event('input'));")
    driver.execute_script("document.getElementById('udhar-amount-input').dispatchEvent(new Event('input'));")
    time.sleep(0.8)

    p4 = os.path.join(OUT_DIR, "04_udhar_add_with_repayment_warning_mobile.png")
    driver.save_screenshot(p4)
    print("   Saved:", p4, f"({os.path.getsize(p4)} bytes)")

    close_u = driver.find_element(By.ID, "udhar-modal-close")
    driver.execute_script("arguments[0].click();", close_u)
    time.sleep(0.5)

    # -------------------------------------------------------------
    # 5. Savings Goals in Settings
    # -------------------------------------------------------------
    print("7. Capturing Screen 5: Savings Goals in Settings...")
    driver.execute_script("window.switchView('settings');")
    time.sleep(2)
    
    card_goals = WebDriverWait(driver, 15).until(
        EC.presence_of_element_located((By.ID, "settings-goals-card"))
    )
    driver.execute_script("arguments[0].scrollIntoView({block: 'start'});", card_goals)
    time.sleep(1)
    p5 = os.path.join(OUT_DIR, "05_savings_goals_mobile.png")
    driver.save_screenshot(p5)
    print("   Saved:", p5, f"({os.path.getsize(p5)} bytes)")

    print("\nALL 5 MOBILE SCREENSHOTS CAPTURED SUCCESSFULLY!")

finally:
    driver.quit()

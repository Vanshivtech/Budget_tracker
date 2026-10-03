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
    
    print("2. Injecting auth...")
    driver.execute_script("""
        sessionStorage.setItem('abt_token', arguments[0]);
        sessionStorage.setItem('abt_user', JSON.stringify(arguments[1]));
        sessionStorage.setItem('abt_onboarding_skipped', '1');
        location.reload();
    """, token, user_display)
    time.sleep(2)
    
    # ---------------------------------------------------------
    # Screen 1: Quick-Add Bar
    # ---------------------------------------------------------
    print("3. Screen 1: Dashboard Quick-Add Bar...")
    driver.execute_script("window.switchView('dashboard');")
    time.sleep(2)
    
    amt = WebDriverWait(driver, 10).until(EC.presence_of_element_located((By.ID, "dashboard-quick-add-wrap-amt")))
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
    print("Saved 1:", p1, "size:", os.path.getsize(p1))

    # ---------------------------------------------------------
    # Screen 2: Transactions View & Edit Modal
    # ---------------------------------------------------------
    print("4. Screen 2: Transactions View & Edit Modal...")
    driver.execute_script("window.switchView('transactions');")
    time.sleep(2)
    
    WebDriverWait(driver, 30).until(
        lambda d: d.find_element(By.ID, "tx-loader").value_of_css_property("display") == "none"
    )
    time.sleep(0.5)
    
    edit_btns = driver.find_elements(By.CLASS_NAME, "btn-edit-tx")
    print(f"Found {len(edit_btns)} edit buttons")
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
        print("Saved 2:", p2, "size:", os.path.getsize(p2))
        
        close_btn = driver.find_element(By.ID, "expense-modal-close")
        driver.execute_script("arguments[0].click();", close_btn)
        time.sleep(0.5)

    # ---------------------------------------------------------
    # Screen 3: Budget Manager in Settings
    # ---------------------------------------------------------
    print("5. Screen 3: Budget Manager in Settings...")
    driver.execute_script("window.switchView('settings');")
    time.sleep(2)
    
    card_bm = WebDriverWait(driver, 10).until(
        EC.presence_of_element_located((By.ID, "settings-budget-manager-card"))
    )
    driver.execute_script("arguments[0].scrollIntoView({block: 'start'});", card_bm)
    time.sleep(1)
    p3 = os.path.join(OUT_DIR, "03_budget_manager_mobile.png")
    driver.save_screenshot(p3)
    print("Saved 3:", p3, "size:", os.path.getsize(p3))

    # ---------------------------------------------------------
    # Screen 4: Udhar Add Form with Repayment Warning
    # ---------------------------------------------------------
    print("6. Screen 4: Udhar Add Form with Repayment Warning...")
    driver.execute_script("window.switchView('udhar');")
    time.sleep(2)
    
    btn_add_u = WebDriverWait(driver, 10).until(
        EC.presence_of_element_located((By.ID, "btn-add-udhar-manual"))
    )
    driver.execute_script("arguments[0].click();", btn_add_u)
    
    WebDriverWait(driver, 10).until(
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
    print("Saved 4:", p4, "size:", os.path.getsize(p4))

    close_u = driver.find_element(By.ID, "udhar-modal-close")
    driver.execute_script("arguments[0].click();", close_u)
    time.sleep(0.5)

    # ---------------------------------------------------------
    # Screen 5: Savings Goals in Settings
    # ---------------------------------------------------------
    print("7. Screen 5: Savings Goals in Settings...")
    driver.execute_script("window.switchView('settings');")
    time.sleep(2)
    
    card_goals = WebDriverWait(driver, 10).until(
        EC.presence_of_element_located((By.ID, "settings-goals-card"))
    )
    driver.execute_script("arguments[0].scrollIntoView({block: 'start'});", card_goals)
    time.sleep(1)
    p5 = os.path.join(OUT_DIR, "05_savings_goals_mobile.png")
    driver.save_screenshot(p5)
    print("Saved 5:", p5, "size:", os.path.getsize(p5))

    print("\nALL 5 MOBILE SCREENSHOTS CAPTURED SUCCESSFULLY!")

finally:
    driver.quit()

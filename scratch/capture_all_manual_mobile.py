"""
Automated 375px mobile viewport screenshots of all manual entry and management features
using Selenium headless Chrome with iPhone SE mobile emulation (375px width).
Order: Transactions -> Udhar -> Settings -> Dashboard
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

demo_email = "manual_demo@budgettracker.local"
user = get_user_by_email(demo_email)
token = create_access_token(user["id"], user["email"])
user_display = get_user_display(user["id"])

opts = Options()
opts.add_argument("--headless=new")
opts.add_experimental_option("mobileEmulation", {"deviceName": "iPhone SE"})
opts.add_argument("--disable-gpu")
opts.add_argument("--no-sandbox")
opts.add_argument("--disable-service-workers")
opts.add_argument("--disable-cache")

driver = webdriver.Chrome(options=opts)

try:
    print("1. Loading app...")
    driver.get("http://127.0.0.1:8000")
    time.sleep(1)

    print("2. Injecting auth session...")
    driver.execute_script("""
        sessionStorage.setItem('abt_token', arguments[0]);
        sessionStorage.setItem('abt_user', JSON.stringify(arguments[1]));
        sessionStorage.setItem('abt_onboarding_skipped', '1');
        location.reload();
    """, token, user_display)
    time.sleep(2)

    # -------------------------------------------------------------
    # 1. Screen 2: Transactions View & Edit Modal
    # -------------------------------------------------------------
    print("3. Capturing Screen 2: Transactions View & Edit Modal...")
    driver.execute_script("window.switchView('transactions');")

    WebDriverWait(driver, 25).until(
        lambda d: len(d.find_elements(By.CLASS_NAME, "btn-edit-tx")) > 0
    )
    time.sleep(1)

    edit_btns = driver.find_elements(By.CLASS_NAME, "btn-edit-tx")
    print(f"Found {len(edit_btns)} edit buttons. Opening edit modal...")
    driver.execute_script("arguments[0].scrollIntoView({block: 'center'});", edit_btns[0])
    time.sleep(0.3)
    driver.execute_script("arguments[0].click();", edit_btns[0])

    WebDriverWait(driver, 10).until(
        lambda d: d.find_element(By.ID, "modal-expense-entry").value_of_css_property("display") != "none"
    )
    time.sleep(1)

    p2 = os.path.join(OUT_DIR, "02_transactions_view_and_edit_modal_mobile.png")
    driver.save_screenshot(p2)
    print("Saved 2:", p2, "size:", os.path.getsize(p2))

    close_btn = driver.find_element(By.ID, "expense-modal-close")
    driver.execute_script("arguments[0].click();", close_btn)
    time.sleep(0.5)
    try:
        driver.switch_to.alert.accept()
    except Exception:
        pass

    # -------------------------------------------------------------
    # 2. Screen 4: Udhar Add Form with Repayment Warning
    # -------------------------------------------------------------
    print("4. Capturing Screen 4: Udhar Add Form with Repayment Warning...")
    driver.execute_script("window.switchView('udhar');")

    WebDriverWait(driver, 25).until(
        lambda d: d.find_element(By.ID, "udhar-content").value_of_css_property("display") != "none"
    )
    time.sleep(1)

    btn_add_u = WebDriverWait(driver, 15).until(
        EC.presence_of_element_located((By.ID, "btn-add-udhar-trigger"))
    )
    driver.execute_script("arguments[0].click();", btn_add_u)

    WebDriverWait(driver, 10).until(
        lambda d: d.find_element(By.ID, "modal-udhar-entry").value_of_css_property("display") != "none"
    )
    time.sleep(0.5)

    kind_sel = Select(driver.find_element(By.ID, "udhar-kind-select"))
    kind_sel.select_by_value("received_back")
    driver.execute_script("document.getElementById('udhar-kind-select').dispatchEvent(new Event('change'));")

    p_in = driver.find_element(By.ID, "udhar-person-input")
    p_in.clear()
    p_in.send_keys("Rahul Sharma")
    a_in = driver.find_element(By.ID, "udhar-amount-input")
    a_in.clear()
    a_in.send_keys("3500")

    driver.execute_script("document.getElementById('udhar-person-input').dispatchEvent(new Event('input'));")
    driver.execute_script("document.getElementById('udhar-amount-input').dispatchEvent(new Event('input'));")
    time.sleep(1)

    p4 = os.path.join(OUT_DIR, "04_udhar_add_with_repayment_warning_mobile.png")
    driver.save_screenshot(p4)
    print("Saved 4:", p4, "size:", os.path.getsize(p4))

    close_u = driver.find_element(By.ID, "udhar-modal-close")
    driver.execute_script("arguments[0].click();", close_u)
    time.sleep(0.5)
    try:
        alert = driver.switch_to.alert
        print("Encountered dirty-form alert:", alert.text)
        alert.accept()
        time.sleep(0.5)
    except Exception:
        pass

    # -------------------------------------------------------------
    # 3. Screen 3: Budget Manager in Settings
    # -------------------------------------------------------------
    print("5. Capturing Screen 3: Budget Manager in Settings...")
    driver.execute_script("window.switchView('settings');")

    WebDriverWait(driver, 25).until(
        lambda d: len(d.find_elements(By.CLASS_NAME, "budget-inline-limit-input")) > 0
    )
    time.sleep(1)

    card_bm = driver.find_element(By.ID, "settings-budget-manager-card")
    driver.execute_script("arguments[0].scrollIntoView({block: 'start'});", card_bm)
    time.sleep(1)

    p3 = os.path.join(OUT_DIR, "03_budget_manager_mobile.png")
    driver.save_screenshot(p3)
    print("Saved 3:", p3, "size:", os.path.getsize(p3))

    # -------------------------------------------------------------
    # 4. Screen 5: Savings Goals in Settings
    # -------------------------------------------------------------
    print("6. Capturing Screen 5: Savings Goals in Settings...")
    card_goals = driver.find_element(By.ID, "settings-goals-card")
    driver.execute_script("arguments[0].scrollIntoView({block: 'start'});", card_goals)
    time.sleep(1)

    p5 = os.path.join(OUT_DIR, "05_savings_goals_mobile.png")
    driver.save_screenshot(p5)
    print("Saved 5:", p5, "size:", os.path.getsize(p5))

    # -------------------------------------------------------------
    # 5. Screen 1: Dashboard Quick-Add Bar Mobile
    # -------------------------------------------------------------
    print("7. Capturing Screen 1: Dashboard Quick-Add Bar...")
    driver.execute_script("window.switchView('dashboard');")
    time.sleep(1)

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

    driver.execute_script("const s = document.querySelector('.dashboard-scroll'); if (s) s.scrollTop = 0; window.scrollTo(0, 0);")
    time.sleep(0.8)
    p1 = os.path.join(OUT_DIR, "01_quick_add_bar_mobile.png")
    driver.save_screenshot(p1)
    print("Saved 1:", p1, "size:", os.path.getsize(p1))

    print("\nALL 5 MOBILE SCREENSHOTS CAPTURED SUCCESSFULLY AT 375PX VIEWPORT!")

finally:
    driver.quit()

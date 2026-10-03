"""
Automated 375px mobile viewport screenshots of the manual entry and management features
using Selenium headless Chrome.
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
opts.add_argument("--window-size=375,812")
opts.add_argument("--disable-gpu")
opts.add_argument("--no-sandbox")

driver = webdriver.Chrome(options=opts)
driver.set_window_size(375, 812)

try:
    print("1. Opening app...")
    driver.get("http://127.0.0.1:8000")
    time.sleep(1)

    print("2. Injecting authenticated session...")
    driver.execute_script("""
        sessionStorage.setItem('abt_token', arguments[0]);
        sessionStorage.setItem('abt_user', JSON.stringify(arguments[1]));
        sessionStorage.setItem('abt_onboarding_skipped', '1');
        location.reload();
    """, token, user_display)
    
    WebDriverWait(driver, 15).until(
        lambda d: d.find_element(By.ID, "app-screen").is_displayed()
    )
    time.sleep(1.5)

    def go_to_view(view_name):
        driver.execute_script("window.switchView(arguments[0]);", view_name)
        time.sleep(2.5)

    # -------------------------------------------------------------
    # 1. Quick-Add Bar Mobile
    # -------------------------------------------------------------
    print("3. Capturing Quick-Add Bar on Dashboard...")
    go_to_view("dashboard")
    
    amt_input = WebDriverWait(driver, 15).until(
        EC.presence_of_element_located((By.ID, "dashboard-quick-add-wrap-amt"))
    )
    amt_input.clear()
    amt_input.send_keys("250")
    note_input = driver.find_element(By.ID, "dashboard-quick-add-wrap-note")
    note_input.clear()
    note_input.send_keys("Coffee & team snacks")
    tag_input = driver.find_element(By.ID, "dashboard-quick-add-wrap-tag")
    tag_input.clear()
    tag_input.send_keys("office")
    
    driver.execute_script("window.scrollTo(0, 0);")
    time.sleep(0.5)
    p1 = os.path.join(OUT_DIR, "01_quick_add_bar_mobile.png")
    driver.save_screenshot(p1)
    print("Saved:", p1, "size:", os.path.getsize(p1))

    # -------------------------------------------------------------
    # 2. Transaction List View & Edit Modal
    # -------------------------------------------------------------
    print("4. Capturing Transaction List & Edit Modal...")
    go_to_view("transactions")
    
    WebDriverWait(driver, 30).until(
        lambda d: d.find_element(By.ID, "tx-loader").value_of_css_property("display") == "none"
    )
    
    edit_btn = WebDriverWait(driver, 20).until(
        EC.presence_of_element_located((By.CLASS_NAME, "btn-edit-tx"))
    )
    driver.execute_script("arguments[0].scrollIntoView({block: 'center'});", edit_btn)
    time.sleep(0.5)
    driver.execute_script("arguments[0].click();", edit_btn)
    
    WebDriverWait(driver, 10).until(
        EC.visibility_of_element_located((By.ID, "modal-expense-entry"))
    )
    time.sleep(0.5)
    p2 = os.path.join(OUT_DIR, "02_transactions_view_and_edit_modal_mobile.png")
    driver.save_screenshot(p2)
    print("Saved:", p2, "size:", os.path.getsize(p2))
    
    # Close modal
    close_btn = driver.find_element(By.ID, "expense-modal-close")
    driver.execute_script("arguments[0].click();", close_btn)
    time.sleep(0.5)

    # -------------------------------------------------------------
    # 3. Budget Manager in Settings
    # -------------------------------------------------------------
    print("5. Capturing Budget Manager...")
    go_to_view("settings")
    card_bm = WebDriverWait(driver, 10).until(
        EC.presence_of_element_located((By.ID, "settings-budget-manager-card"))
    )
    driver.execute_script("arguments[0].scrollIntoView({block: 'start'});", card_bm)
    time.sleep(1)
    p3 = os.path.join(OUT_DIR, "03_budget_manager_mobile.png")
    driver.save_screenshot(p3)
    print("Saved:", p3, "size:", os.path.getsize(p3))

    # -------------------------------------------------------------
    # 4. Udhar Add Form with Repayment Warning
    # -------------------------------------------------------------
    print("6. Capturing Udhar Add Form with Repayment Balance Warning...")
    go_to_view("udhar")
    time.sleep(1)
    btn_add_udhar = WebDriverWait(driver, 10).until(
        EC.presence_of_element_located((By.ID, "btn-add-udhar-manual"))
    )
    driver.execute_script("arguments[0].click();", btn_add_udhar)
    
    WebDriverWait(driver, 10).until(
        EC.visibility_of_element_located((By.ID, "modal-udhar-entry"))
    )
    time.sleep(0.5)

    # Select direction: received_back
    kind_sel = Select(driver.find_element(By.ID, "udhar-entry-kind"))
    kind_sel.select_by_value("received_back")
    driver.execute_script("document.getElementById('udhar-entry-kind').dispatchEvent(new Event('change'));")
    
    # Enter person and excessive amount
    person_in = driver.find_element(By.ID, "udhar-person-input")
    person_in.clear()
    person_in.send_keys("Rahul Sharma")
    amt_in = driver.find_element(By.ID, "udhar-amount-input")
    amt_in.clear()
    amt_in.send_keys("3500")

    # Trigger input events to trigger client-side balance calculation
    driver.execute_script("document.getElementById('udhar-person-input').dispatchEvent(new Event('input'));")
    driver.execute_script("document.getElementById('udhar-amount-input').dispatchEvent(new Event('input'));")
    time.sleep(0.8)

    p4 = os.path.join(OUT_DIR, "04_udhar_add_with_repayment_warning_mobile.png")
    driver.save_screenshot(p4)
    print("Saved:", p4, "size:", os.path.getsize(p4))

    # Close modal
    close_u = driver.find_element(By.ID, "udhar-modal-close")
    driver.execute_script("arguments[0].click();", close_u)
    time.sleep(0.5)

    # -------------------------------------------------------------
    # 5. Savings Goals in Settings
    # -------------------------------------------------------------
    print("7. Capturing Savings Goals...")
    go_to_view("settings")
    card_goals = WebDriverWait(driver, 10).until(
        EC.presence_of_element_located((By.ID, "settings-goals-card"))
    )
    driver.execute_script("arguments[0].scrollIntoView({block: 'start'});", card_goals)
    time.sleep(1)
    p5 = os.path.join(OUT_DIR, "05_savings_goals_mobile.png")
    driver.save_screenshot(p5)
    print("Saved:", p5, "size:", os.path.getsize(p5))

    print("\nAll 5 mobile screenshots successfully captured and verified!")

finally:
    driver.quit()

"""
Automated desktop browser screenshots of the Admin Panel and User Settings
using Selenium headless Chrome at 1440x900 desktop width.
"""
import time
import os
import sys
sys.path.insert(0, ".")

from selenium import webdriver
from selenium.webdriver.chrome.options import Options
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC

from app.db import create_user, get_user_by_email, complete_onboarding, delete_account
from app.auth import hash_password

OUT_DIR = os.path.abspath("scratch/screenshots")
os.makedirs(OUT_DIR, exist_ok=True)

# Prepare a verified demo user
demo_email = "demouser_settings@budgettracker.local"
demo_pwd = "DemoPassword123!"
existing = get_user_by_email(demo_email)
if existing:
    delete_account(existing["id"])
demo_user = create_user(demo_email, hash_password(demo_pwd))
complete_onboarding(demo_user["id"], "living_alone", 60000.0, [{"name": "Groceries", "amount": 12000.0, "enabled": True}])

opts = Options()
opts.add_argument("--headless=new")
opts.add_argument("--window-size=1440,960")
opts.add_argument("--disable-gpu")
opts.add_argument("--no-sandbox")

driver = webdriver.Chrome(options=opts)
driver.set_window_size(1440, 960)

try:
    print("1. Opening /admin unauthenticated...")
    driver.get("http://127.0.0.1:8000/admin")
    WebDriverWait(driver, 10).until(
        EC.visibility_of_element_located((By.ID, "admin-login-view"))
    )
    time.sleep(1)
    p1 = os.path.join(OUT_DIR, "01_admin_login.png")
    driver.save_screenshot(p1)
    print("Saved:", p1)

    print("2. Logging into admin panel...")
    email_input = driver.find_element(By.ID, "admin-email")
    pwd_input = driver.find_element(By.ID, "admin-password")
    submit_btn = driver.find_element(By.ID, "btn-login-submit")

    email_input.send_keys("admin@budgettracker.local")
    pwd_input.send_keys("AdminPassword2026!")
    submit_btn.click()

    WebDriverWait(driver, 10).until(
        EC.visibility_of_element_located((By.ID, "admin-portal-view"))
    )
    # Wait for dashboard data to load
    WebDriverWait(driver, 10).until(
        lambda d: d.find_element(By.ID, "kpi-total-users").text not in ("0", "")
    )
    time.sleep(1)
    p2 = os.path.join(OUT_DIR, "02_admin_dashboard.png")
    driver.save_screenshot(p2)
    print("Saved:", p2)

    print("3. Navigating to Users table...")
    users_tab = driver.find_element(By.XPATH, "//button[@data-tab='users']")
    users_tab.click()
    WebDriverWait(driver, 10).until(
        EC.presence_of_element_located((By.CSS_SELECTOR, "#users-table-tbody tr td"))
    )
    time.sleep(1)
    p3 = os.path.join(OUT_DIR, "03_admin_users.png")
    driver.save_screenshot(p3)
    print("Saved:", p3)

    print("4. Opening User Detail Panel...")
    view_btn = driver.find_element(By.CSS_SELECTOR, ".btn-view-user")
    view_btn.click()
    WebDriverWait(driver, 10).until(
        EC.visibility_of_element_located((By.ID, "modal-user-detail"))
    )
    time.sleep(1)
    p4 = os.path.join(OUT_DIR, "04_admin_user_detail.png")
    driver.save_screenshot(p4)
    print("Saved:", p4)

    close_btn = driver.find_element(By.ID, "btn-close-user-detail")
    close_btn.click()
    time.sleep(0.5)

    print("5. Navigating to LLM Usage...")
    llm_tab = driver.find_element(By.XPATH, "//button[@data-tab='llm']")
    llm_tab.click()
    WebDriverWait(driver, 10).until(
        EC.presence_of_element_located((By.CSS_SELECTOR, "#top-users-tbody tr"))
    )
    time.sleep(1)
    p5 = os.path.join(OUT_DIR, "05_admin_llm_usage.png")
    driver.save_screenshot(p5)
    print("Saved:", p5)

    print("6. Navigating to DB Explorer...")
    exp_tab = driver.find_element(By.XPATH, "//button[@data-tab='explorer']")
    exp_tab.click()
    WebDriverWait(driver, 10).until(
        EC.presence_of_element_located((By.CSS_SELECTOR, "#explorer-table-selector button"))
    )
    WebDriverWait(driver, 10).until(
        EC.presence_of_element_located((By.CSS_SELECTOR, "#explorer-tbody tr"))
    )
    time.sleep(1)
    p6 = os.path.join(OUT_DIR, "06_admin_db_explorer.png")
    driver.save_screenshot(p6)
    print("Saved:", p6)

    print("7. Navigating to App Settings...")
    set_tab = driver.find_element(By.XPATH, "//button[@data-tab='settings']")
    set_tab.click()
    time.sleep(1)
    p7 = os.path.join(OUT_DIR, "07_admin_app_settings.png")
    driver.save_screenshot(p7)
    print("Saved:", p7)

    print("8. Navigating to User App to test Settings -> Change Password form...")
    driver.get("http://127.0.0.1:8000")
    WebDriverWait(driver, 10).until(
        EC.visibility_of_element_located((By.ID, "auth-screen"))
    )
    # Log in as demo user
    u_email = driver.find_element(By.ID, "auth-email")
    u_pwd = driver.find_element(By.ID, "auth-password")
    u_btn = driver.find_element(By.ID, "auth-submit-btn")
    u_email.send_keys(demo_email)
    u_pwd.send_keys(demo_pwd)
    u_btn.click()

    WebDriverWait(driver, 10).until(
        EC.visibility_of_element_located((By.ID, "app-screen"))
    )
    time.sleep(1.5)

    # Click Settings Nav
    settings_nav = driver.find_element(By.ID, "nav-settings")
    settings_nav.click()
    time.sleep(1)

    # Scroll to change password card
    pwd_card = driver.find_element(By.ID, "settings-change-password-card")
    driver.execute_script("arguments[0].scrollIntoView({behavior: 'instant', block: 'center'});", pwd_card)
    time.sleep(1)

    p8 = os.path.join(OUT_DIR, "08_user_change_password.png")
    driver.save_screenshot(p8)
    print("Saved:", p8)

    print("All screenshots captured successfully!")

finally:
    driver.quit()

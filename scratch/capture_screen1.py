"""
Capture Screen 1: Dashboard Quick-Add Bar at 375px mobile viewport.
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

    print("3. Switching to dashboard...")
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

    # Scroll top
    driver.execute_script("""
        const s = document.querySelector('.dashboard-scroll');
        if (s) s.scrollTop = 0;
        window.scrollTo(0, 0);
    """)
    time.sleep(0.8)

    p1 = os.path.join(OUT_DIR, "01_quick_add_bar_mobile.png")
    driver.save_screenshot(p1)
    print("Saved 1:", p1, "size:", os.path.getsize(p1))

finally:
    driver.quit()

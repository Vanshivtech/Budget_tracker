import os
import time
from selenium import webdriver
from selenium.webdriver.chrome.options import Options
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC

opts = Options()
opts.add_argument("--headless=new")
opts.add_argument("--window-size=1440,960")
opts.add_argument("--disable-gpu")
opts.add_argument("--no-sandbox")
driver = webdriver.Chrome(options=opts)
driver.set_window_size(1440, 960)

try:
    driver.get("http://127.0.0.1:8000")
    WebDriverWait(driver, 10).until(EC.visibility_of_element_located((By.ID, "auth-screen")))
    driver.find_element(By.ID, "auth-email").send_keys("demouser_settings@budgettracker.local")
    driver.find_element(By.ID, "auth-password").send_keys("DemoPassword123!")
    driver.find_element(By.ID, "auth-submit-btn").click()
    WebDriverWait(driver, 10).until(EC.visibility_of_element_located((By.ID, "app-screen")))
    time.sleep(1.5)
    
    # Click Settings tab
    settings_btn = driver.find_element(By.ID, "nav-settings")
    settings_btn.click()
    time.sleep(1)
    
    pwd_card = driver.find_element(By.ID, "settings-change-password-card")
    driver.execute_script("arguments[0].scrollIntoView({behavior: 'instant', block: 'center'});", pwd_card)
    time.sleep(1)
    
    out_path = "scratch/screenshots/08_user_change_password.png"
    driver.save_screenshot(out_path)
    print("Screenshot saved, size:", os.path.getsize(out_path))
except Exception as e:
    print("Error:", e)
finally:
    driver.quit()

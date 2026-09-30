import sys
import time
sys.stdout.reconfigure(encoding='utf-8')
from selenium import webdriver
from selenium.webdriver.chrome.options import Options
from selenium.webdriver.common.by import By
from selenium.webdriver.common.keys import Keys

copts = Options()
copts.add_argument("--headless")
copts.add_argument("--window-size=1280,800")
driver = webdriver.Chrome(options=copts)

try:
    driver.get("http://localhost:8000/")
    time.sleep(1)
    driver.find_element(By.ID, "auth-email").send_keys("test@example.com")
    pass_input = driver.find_element(By.ID, "auth-password")
    pass_input.send_keys("test1234")
    pass_input.send_keys(Keys.ENTER)
    time.sleep(3)

    # Click nav-dashboard using JS click to be 100% sure
    dash_btn = driver.find_element(By.ID, "nav-dashboard")
    print("dash_btn text:", dash_btn.text)
    driver.execute_script("arguments[0].click();", dash_btn)
    
    for i in range(15):
        time.sleep(1)
        panel_class = driver.find_element(By.ID, "view-dashboard").get_attribute("class")
        loader_disp = driver.find_element(By.ID, "dashboard-loader").value_of_css_property("display")
        content_disp = driver.find_element(By.ID, "dashboard-content").value_of_css_property("display")
        print(f"t={i+1}s: panel_class={panel_class}, loader_disp={loader_disp}, content_disp={content_disp}")
        if loader_disp == "none" and content_disp != "none":
            print("Dashboard loaded successfully!")
            break

    driver.save_screenshot("dash_debug.png")
finally:
    driver.quit()

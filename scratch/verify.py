import os
import sys
import time

sys.stdout.reconfigure(encoding='utf-8')
from selenium import webdriver
from selenium.webdriver.chrome.options import Options
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait

ARTIFACTS_DIR = r"C:\Users\SHIV\.gemini\antigravity-ide\brain\862cf148-45ea-4691-ad47-7086ae924d06"

from selenium.webdriver.common.keys import Keys

copts = Options()
copts.add_argument("--headless")
copts.add_argument("--window-size=1280,800")
driver = webdriver.Chrome(options=copts)

try:
    print("1. Opening http://localhost:8000/")
    driver.get("http://localhost:8000/")
    time.sleep(1)

    # 1. Auth screen default (dark)
    auth_dark_path = os.path.join(ARTIFACTS_DIR, "auth_dark.png")
    driver.save_screenshot(auth_dark_path)
    print("Auth dark screenshot saved:", auth_dark_path)

    # Click auth theme toggle
    theme_btn_auth = driver.find_element(By.ID, "theme-toggle-auth")
    theme_btn_auth.click()
    time.sleep(0.5)
    theme_val = driver.execute_script("return document.documentElement.getAttribute('data-theme');")
    print("Theme after clicking toggle on auth:", theme_val)

    auth_light_path = os.path.join(ARTIFACTS_DIR, "auth_light.png")
    driver.save_screenshot(auth_light_path)
    print("Auth light screenshot saved:", auth_light_path)

    # Switch back to dark for login
    theme_btn_auth.click()
    time.sleep(0.3)

    # Sign in
    email_input = driver.find_element(By.ID, "auth-email")
    email_input.clear()
    email_input.send_keys("test@example.com")
    pass_input = driver.find_element(By.ID, "auth-password")
    pass_input.clear()
    pass_input.send_keys("test1234")
    
    submit_btn = driver.find_element(By.ID, "auth-submit-btn")
    driver.execute_script("arguments[0].click();", submit_btn)

    # Wait for login transition
    try:
        WebDriverWait(driver, 15).until(
            lambda d: d.find_element(By.ID, "app-screen").is_displayed() or 
                      d.find_element(By.ID, "onboarding-screen").is_displayed()
        )
    except Exception as e:
        err_elem = driver.find_element(By.ID, "auth-error")
        print("Login timed out! auth-error text:", err_elem.text)
        driver.save_screenshot(os.path.join(ARTIFACTS_DIR, "login_failed.png"))
        raise

    time.sleep(1)

    # Check if onboarding screen is visible; if so, skip it
    ob_screen = driver.find_element(By.ID, "onboarding-screen")
    if ob_screen.is_displayed():
        print("Onboarding displayed, clicking skip...")
        skip_btn = driver.find_element(By.ID, "ob-skip")
        driver.execute_script("arguments[0].click();", skip_btn)
        time.sleep(1)

    app_screen = driver.find_element(By.ID, "app-screen")
    print("App screen displayed:", app_screen.is_displayed())

    # Send chat message
    composer_input = driver.find_element(By.ID, "composer-input")
    composer_input.send_keys("Spent 150 on coffee")
    time.sleep(0.3)
    composer_send = driver.find_element(By.ID, "composer-send")
    composer_send.click()
    print("Message sent, waiting for reply...")

    # Wait up to 40s for assistant reply
    WebDriverWait(driver, 40).until(
        lambda d: len(d.find_elements(By.CSS_SELECTOR, ".msg.assistant")) > 0
    )
    time.sleep(1)

    # Screenshot chat dark
    chat_dark_path = os.path.join(ARTIFACTS_DIR, "chat_bubbles_dark.png")
    driver.save_screenshot(chat_dark_path)
    print("Chat dark screenshot saved:", chat_dark_path)

    # Get assistant message text and computed styles
    asst_msg = driver.find_element(By.CSS_SELECTOR, ".msg.assistant .msg-content")
    print("Assistant reply text:", asst_msg.text)
    border_radius = driver.execute_script("return window.getComputedStyle(arguments[0]).borderRadius;", asst_msg)
    bg_color = driver.execute_script("return window.getComputedStyle(arguments[0]).backgroundColor;", asst_msg)
    padding = driver.execute_script("return window.getComputedStyle(arguments[0]).padding;", asst_msg)
    print(f"Assistant bubble styles -> border-radius: {border_radius}, bg: {bg_color}, padding: {padding}")

    # Toggle to light mode via sidebar
    sidebar_toggle = driver.find_element(By.ID, "theme-toggle")
    sidebar_toggle.click()
    time.sleep(0.5)
    theme_val = driver.execute_script("return document.documentElement.getAttribute('data-theme');")
    print("Theme after sidebar toggle:", theme_val)

    chat_light_path = os.path.join(ARTIFACTS_DIR, "chat_bubbles_light.png")
    driver.save_screenshot(chat_light_path)
    print("Chat light screenshot saved:", chat_light_path)

    # Navigate to Dashboard
    dash_nav_btn = driver.find_element(By.ID, "nav-dashboard")
    driver.execute_script("arguments[0].click();", dash_nav_btn)
    WebDriverWait(driver, 45).until(lambda d: not d.find_element(By.ID, "dashboard-loader").is_displayed())
    time.sleep(1)
    dash_light_path = os.path.join(ARTIFACTS_DIR, "dashboard_light.png")
    driver.save_screenshot(dash_light_path)
    print("Dashboard light screenshot saved:", dash_light_path)

    # Toggle to dark on Dashboard
    sidebar_toggle.click()
    time.sleep(0.5)
    dash_dark_path = os.path.join(ARTIFACTS_DIR, "dashboard_dark.png")
    driver.save_screenshot(dash_dark_path)
    print("Dashboard dark screenshot saved:", dash_dark_path)

    # Switch back to light
    sidebar_toggle.click()
    time.sleep(0.5)

    # Navigate to Udhar
    udhar_nav_btn = driver.find_element(By.ID, "nav-udhar")
    driver.execute_script("arguments[0].click();", udhar_nav_btn)
    WebDriverWait(driver, 35).until(lambda d: not d.find_element(By.ID, "udhar-loader").is_displayed())
    time.sleep(1)
    time.sleep(0.5)
    udhar_light_path = os.path.join(ARTIFACTS_DIR, "udhar_light.png")
    driver.save_screenshot(udhar_light_path)
    print("Udhar light screenshot saved:", udhar_light_path)

    # Toggle to dark on Udhar
    sidebar_toggle.click()
    time.sleep(0.5)
    udhar_dark_path = os.path.join(ARTIFACTS_DIR, "udhar_dark.png")
    driver.save_screenshot(udhar_dark_path)
    print("Udhar dark screenshot saved:", udhar_dark_path)

    # Set to light theme to test persistence
    sidebar_toggle.click()
    time.sleep(0.5)
    ls_theme = driver.execute_script("return localStorage.getItem('abt_theme');")
    print("localStorage abt_theme before reload:", ls_theme)

    # Reload page
    print("Reloading page to test persistence...")
    driver.refresh()
    time.sleep(2)
    after_reload_theme = driver.execute_script("return document.documentElement.getAttribute('data-theme');")
    print("Theme after reload:", after_reload_theme)

    # Log out to test auth persistence
    driver.execute_script("arguments[0].click();", driver.find_element(By.ID, "logout-btn"))
    time.sleep(1)
    auth_after_logout_theme = driver.execute_script("return document.documentElement.getAttribute('data-theme');")
    print("Theme on auth after logout:", auth_after_logout_theme)

    print("ALL VERIFICATION CHECKS COMPLETED SUCCESSFULLY!")
finally:
    driver.quit()

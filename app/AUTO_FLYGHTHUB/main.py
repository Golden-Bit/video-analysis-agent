from selenium import webdriver
from selenium.webdriver.chrome.service import Service
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from selenium.webdriver.common.keys import Keys
from selenium.webdriver.common.action_chains import ActionChains
import time

# Credenziali
USERNAME = "xr01.theia@gmail.com"
PASSWORD = "LBFL2hFxFwUTKc5"

# Nome del piano
PLAN_NAME = "MyTestPlan"

# Nome della rotta da selezionare
ROUTE_NAME = "Test fotovoltaico"

# URL di login DJI
LOGIN_URL = (
    "https://account.dji.com/login?"
    "appId=es310-manage-service-prod-vg&"
    "backUrl=https%3A%2F%2Ffh.dji.com&"
    "locale=en_US"
)

chrome_driver_path = r"drivers/drivers/chrome/chromedriver-win64/chromedriver.exe"
service = Service(executable_path=chrome_driver_path)

def main():
    driver = webdriver.Chrome(service=service)
    wait = WebDriverWait(driver, 90)  # Timeout massimo

    try:
        # (1) Apre la pagina di login DJI
        driver.get(LOGIN_URL)
        time.sleep(3)

        # (2) Inserisce username e password
        email_input = driver.find_element(By.NAME, "username")
        email_input.clear()
        email_input.send_keys(USERNAME)

        password_input = driver.find_element(By.CSS_SELECTOR, "input[aria-label='Password']")
        password_input.clear()
        password_input.send_keys(PASSWORD)

        login_button = driver.find_element(By.CSS_SELECTOR, "button[data-usagetag='login_button']")
        login_button.click()

        # (3) Clicca sull’icona "enter-icon" (ripete il click se necessario)
        stop = False
        while not stop:
            stop = True
            try:
                enter_button = wait.until(
                    EC.element_to_be_clickable(
                        (By.CSS_SELECTOR, "div.project-enter.project-enter-btn span.enter-icon.uranus-icon")
                    )
                )
                enter_button.click()
            except Exception as e:
                print(f"[Info] Attendo 'enter-icon': {e}")
                stop = False

        # (4) Clicca sul link che porta a "#/plan"
        plan_link = wait.until(
            EC.element_to_be_clickable((By.CSS_SELECTOR, "a.menu-item[href='#/plan']"))
        )
        plan_link.click()
        time.sleep(5)  # Attesa per il caricamento della pagina "Plan"

        # (5) Clicca sul pulsante "Create Plan"
        create_plan_button = wait.until(
            EC.element_to_be_clickable(
                (By.CSS_SELECTOR, "button.uranus-btn.uranus-btn-primary.uranus-btn-lg.uranus-btn-light")
            )
        )
        create_plan_button.click()

        # (6) Inserisce il nome del piano
        plan_input = wait.until(
            EC.visibility_of_element_located((
                By.CSS_SELECTOR,
                "input.uranus-form-row.uranus-input.uranus-dark.uranus-form-row[maxlength='50']"
            ))
        )
        plan_input.clear()
        plan_input.send_keys(Keys.CONTROL + "a")
        plan_input.send_keys(Keys.DELETE)
        plan_input.send_keys(PLAN_NAME)

        # (7) Clicca sul pulsante "Select Route"
        select_route_xpath = (
            "//button[contains(@class, 'uranus-btn-primary') and "
            "(contains(., 'Select Route') or contains(.//span, 'Select Route'))]"
        )
        select_route_button = wait.until(
            EC.visibility_of_element_located((By.XPATH, select_route_xpath))
        )
        driver.execute_script("arguments[0].scrollIntoView(true);", select_route_button)
        time.sleep(1)
        try:
            driver.execute_script("arguments[0].click();", select_route_button)
        except Exception as e:
            print(f"[Warning] JS click su 'Select Route' fallito: {e}")
            ActionChains(driver).move_to_element(select_route_button).click().perform()

        # (8) Seleziona la rotta “Test fotovoltaico”
        route_xpath = (
            "//div[contains(@class, 'component-plan-app-wayline-item')]"
            "//span[@class='uranus-ellipsis-span ellipsis' and normalize-space(text())='{name}']"
        ).format(name=ROUTE_NAME)
        desired_route_element = wait.until(
            EC.element_to_be_clickable((By.XPATH, route_xpath))
        )
        desired_route_element.click()

        # (9) Clicca sul pulsante "Select Device"
        select_device_xpath = (
            "//button[contains(@class, 'uranus-btn-primary') and "
            "(contains(., 'Select Device') or contains(.//span, 'Select Device'))]"
        )
        select_device_button = wait.until(
            EC.visibility_of_element_located((By.XPATH, select_device_xpath))
        )
        driver.execute_script("arguments[0].scrollIntoView(true);", select_device_button)
        time.sleep(1)
        try:
            driver.execute_script("arguments[0].click();", select_device_button)
        except Exception as e:
            print(f"[Warning] JS click su 'Select Device' fallito: {e}")
            ActionChains(driver).move_to_element(select_device_button).click().perform()

        # (10) Attende che il popup dei device sia visibile
        time.sleep(3)

        # (11) Clicca direttamente sul PRIMO device presente nella lista
        device_xpath = (
            "//div[contains(@class, 'device-select-list')]"
            "//div[contains(@class, 'uranus-tsa-device-item-wrapper')][1]"
        )
        first_device_wrapper = wait.until(
            EC.visibility_of_element_located((By.XPATH, device_xpath))
        )
        driver.execute_script("arguments[0].scrollIntoView(true);", first_device_wrapper)
        time.sleep(1)
        try:
            driver.execute_script("arguments[0].click();", first_device_wrapper)
        except Exception as e:
            print(f"[Warning] JS click sul device fallito: {e}")
            ActionChains(driver).move_to_element(first_device_wrapper).click().perform()

        # (12) Inserisce il valore 50 nel campo "RTH Altitude (Relative to dock)"
        altitude_input = wait.until(
            EC.visibility_of_element_located(
                (By.CSS_SELECTOR, "div.plan-app-ant-input-number-input-wrap input[role='spinbutton']")
            )
        )
        altitude_input.clear()
        altitude_input.send_keys("50")
        time.sleep(1)

        # (13) Clicca sul pulsante "OK" per confermare il piano di volo
        ok_button_xpath = (
            "//div[contains(@class, 'actions')]//button[contains(@class, 'uranus-btn-primary') and contains(., 'OK')]"
        )
        ok_button = wait.until(
            EC.element_to_be_clickable((By.XPATH, ok_button_xpath))
        )
        driver.execute_script("arguments[0].scrollIntoView(true);", ok_button)
        time.sleep(1)
        try:
            driver.execute_script("arguments[0].click();", ok_button)
        except Exception as e:
            print(f"[Warning] JS click su 'OK' fallito: {e}")
            ActionChains(driver).move_to_element(ok_button).click().perform()

        # (14) Attende alcuni secondi per le verifiche finali
        time.sleep(10)

    finally:
        driver.quit()

if __name__ == "__main__":
    main()

from selenium import webdriver
from selenium.webdriver.chrome.service import Service
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from selenium.webdriver.common.keys import Keys
from selenium.webdriver.common.action_chains import ActionChains
import time
import os

# Credenziali
USERNAME = "xr01.theia@gmail.com"
PASSWORD = "LBFL2hFxFwUTKc5"

# URL di login e URL del Cockpit
LOGIN_URL = (
    "https://account.dji.com/login?"
    "appId=es310-manage-service-prod-vg&"
    "backUrl=https%3A%2F%2Ffh.dji.com&"
    "locale=en_US"
)
COCKPIT_URL = (
    "https://fh.dji.com/organization/c7172441-3df9-4e5b-85d8-97c985893b7c/"
    "project/b577be18-d159-459f-ada8-76a0dd08b3b8?"
    "droneSn=1581F6Q8D246N001Q1VE&gatewaySn=7CTXM8M00B00NS#/cockpit"
)

chrome_driver_path = r"app/AUTO_FLYGHTHUB/drivers/chrome/chromedriver-win64/chromedriver.exe"
service = Service(executable_path=chrome_driver_path)

def main():
    driver = webdriver.Chrome(service=service)
    wait = WebDriverWait(driver, 90)  # Timeout massimo per gli elementi

    try:
        # 1. Apertura pagina di login DJI
        driver.get(LOGIN_URL)
        time.sleep(3)  # Attesa iniziale

        # NUOVO: Clic sul pulsante del banner dei cookie ("Required Only")
        cookie_button = wait.until(
            EC.element_to_be_clickable((By.CSS_SELECTOR, "button.cc-consent-require-only.cc-btn.cc-btn-default"))
        )
        cookie_button.click()
        time.sleep(1)

        # 2. Inserimento delle credenziali
        email_input = wait.until(EC.visibility_of_element_located((By.NAME, "username")))
        email_input.clear()
        email_input.send_keys(USERNAME)

        password_input = driver.find_element(By.CSS_SELECTOR, "input[aria-label='Password']")
        password_input.clear()
        password_input.send_keys(PASSWORD)

        login_button = driver.find_element(By.CSS_SELECTOR, "button[data-usagetag='login_button']")
        login_button.click()

        # Attesa per completamento login
        time.sleep(10)

        # 3. Navigazione diretta alla pagina Cockpit
        driver.get(COCKPIT_URL)
        time.sleep(5)
        # 4a. Se appare il dialog dei Keyboard Shortcuts, chiudilo cliccando sull'icona "close"
        try:
            keyboard_dialog_close = wait.until(
                EC.element_to_be_clickable(
                    (By.CSS_SELECTOR, "div.cockpit-keyboard-description div.header span.uranus-icon.uranus-icon-cursor-pointer")
                )
            )
            driver.execute_script("arguments[0].scrollIntoView(true);", keyboard_dialog_close)
            time.sleep(1)
            keyboard_dialog_close.click()
            print("Dialog Keyboard Shortcuts chiuso.")
        except Exception as e:
            print("Dialog Keyboard Shortcuts non presente o già chiuso:", e)

        # Attesa per la stabilizzazione della pagina
        time.sleep(5)

        # 4. Attesa e click sul pulsante "OK" del popup
        modal_ok_button = wait.until(
            EC.element_to_be_clickable(
                (By.XPATH, "//div[@role='document' and contains(@class, 'cockpit-app-ant-modal')]"
                           "//button[.//span[normalize-space()='OK']]")
            )
        )
        driver.execute_script("arguments[0].scrollIntoView(true);", modal_ok_button)
        time.sleep(1)
        modal_ok_button.click()

        # Attesa per la stabilizzazione della pagina
        time.sleep(5)

        # 6. Verifica se esiste il pulsante "Reconnect" e, se esiste, cliccalo.
        try:
            reconnect_button = wait.until(
                EC.element_to_be_clickable((By.CSS_SELECTOR, "div.delay-info-reconnect"))
            )
            driver.execute_script("arguments[0].scrollIntoView(true);", reconnect_button)
            time.sleep(1)
            reconnect_button.click()
            print("Pulsante Reconnect cliccato.")
        except Exception as e:
            print("Pulsante Reconnect non presente:", e)

        # 5. Creazione della cartella per salvare i frame (se non esiste)
        output_folder = "OUTPUT_FRAMES"
        if not os.path.exists(output_folder):
            os.makedirs(output_folder)

        # 6. Estrazione dei frame dal video streammato per 300 secondi
        start_time = time.time()
        end_time = start_time + 300  # 300 secondi = 5 minuti
        while time.time() < end_time:
            try:
                # Individua l'elemento che contiene il video stream (la maschera live)
                stream_element = driver.find_element(By.CSS_SELECTOR, "div.cockpit-realtime-live-mask")
                # Genera un nome file basato sul timestamp (in millisecondi)
                timestamp = int(time.time() * 1000)
                filename = os.path.join(output_folder, f"frame_{timestamp}.png")
                # Salva lo screenshot dell'elemento
                stream_element.screenshot(filename)
                print(f"Saved frame: {filename}")
            except Exception as e:
                print("Error capturing frame:", e)
            # Attesa tra un frame e l'altro (regola l'intervallo se necessario)
            time.sleep(1)

    finally:
        driver.quit()

if __name__ == "__main__":
    main()

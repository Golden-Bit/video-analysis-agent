from selenium import webdriver
from selenium.webdriver.chrome.service import Service
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
import time

# Credenziali
USERNAME = "xr01.theia@gmail.com"
PASSWORD = "LBFL2hFxFwUTKc5"

# URL di login DJI
LOGIN_URL = (
    "https://account.dji.com/login?"
    "appId=es310-manage-service-prod-vg&"
    "backUrl=https%3A%2F%2Ffh.dji.com&"
    "locale=en_US"
)

chrome_driver_path = r"app/AUTO_FLYGHTHUB/drivers/chrome/chromedriver-win64/chromedriver.exe"
service = Service(executable_path=chrome_driver_path)


def main(plan_name: str = "MyTestPlan"):
    driver = webdriver.Chrome(service=service)
    wait = WebDriverWait(driver, 90)  # Timeout massimo
    # Lista che conterrà i nomi dei file
    file_names = []

    try:
        # (1) Apre la pagina di login DJI
        driver.get(LOGIN_URL)
        time.sleep(3)

        # Clic sul pulsante del banner dei cookie ("Required Only")
        cookie_button = wait.until(
            EC.element_to_be_clickable((By.CSS_SELECTOR, "button.cc-consent-require-only.cc-btn.cc-btn-default"))
        )
        cookie_button.click()
        time.sleep(1)

        # (2) Inserisce username e password
        email_input = driver.find_element(By.NAME, "username")
        email_input.clear()
        email_input.send_keys(USERNAME)

        password_input = driver.find_element(By.CSS_SELECTOR, "input[aria-label='Password']")
        password_input.clear()
        password_input.send_keys(PASSWORD)

        login_button = driver.find_element(By.CSS_SELECTOR, "button[data-usagetag='login_button']")
        login_button.click()

        # (3) Clicca sull’icona "enter-icon" (ripetendo se necessario)
        entered = False
        while not entered:
            try:
                enter_button = wait.until(
                    EC.element_to_be_clickable(
                        (By.CSS_SELECTOR, "div.project-enter.project-enter-btn span.enter-icon.uranus-icon")
                    )
                )
                enter_button.click()
                entered = True
            except Exception as e:
                print(f"[Info] Attendo 'enter-icon': {e}")
                time.sleep(1)

        # (4) Clicca sull'icona per accedere ai Media/Files
        media_icon = wait.until(
            EC.element_to_be_clickable((By.CSS_SELECTOR, 'a.menu-item[href="#/media"]'))
        )
        media_icon.click()

        # (5) Attende il caricamento del campo di ricerca e inserisce la stringa "MyTestPlan"
        search_input = wait.until(
            EC.presence_of_element_located((
                By.CSS_SELECTOR,
                "span.search.uranus-custom-input.uranus-custom-input-light.disk-app-ant-input-affix-wrapper.disk-app-ant-input-affix-wrapper-lg input"
            ))
        )
        search_input.clear()
        search_input.send_keys(plan_name)

        # (6) Attende qualche secondo affinché il filtro venga applicato e la lista aggiornata
        time.sleep(3)

        # (7) Clicca sul testo del nome della cartella del primo risultato filtrato.
        first_folder_name = wait.until(
            EC.element_to_be_clickable((
                By.XPATH,
                "(//div[@class='name-tag-container']//span[contains(@class, 'uranus-ellipsis-span') and contains(text(), '" + plan_name + "')])[1]"
            ))
        )
        first_folder_name.click()
        print("Cliccato sul nome del primo folder filtrato.")

        # (8) Attende il caricamento della lista dei file contenuti nella cartella
        list_container = wait.until(
            EC.presence_of_element_located((By.CSS_SELECTOR, "div.document-content"))
        )
        # Tempo per il caricamento completo della lista
        time.sleep(3)

        # Nuovo: Estrae i nomi dei file dalla lista
        file_rows = driver.find_elements(By.XPATH,
                                         "//div[contains(@class, 'document-content')]//table[contains(@class, 'vxe-table--body')]//tbody//tr")
        for row in file_rows:
            try:
                # Seleziona lo span che contiene il nome del file
                name_element = row.find_element(By.CSS_SELECTOR,
                                                "div.name-tag-container div.file-name span.uranus-ellipsis-span")
                file_name = name_element.text.strip()
                if file_name:
                    file_names.append(file_name)
            except Exception as e:
                print("Errore nell'estrazione del nome del file:", e)

        # (9) Clicca sul download dei primi due file, se presenti.
        if len(file_rows) < 2:
            print("Non sono stati trovati almeno due file nella cartella per il download.")
        else:
            # Ordina: prima il secondo file (indice 1) e poi il primo (indice 0)
            rows_to_download = [file_rows[1], file_rows[0]]
            for idx, row in enumerate(rows_to_download):
                try:
                    # Individua la cella delle operazioni (colonna download)
                    operations_cell = row.find_element(By.CSS_SELECTOR, "td.vxe-body--column.col_9")
                    # Trova tutti gli elementi cliccabili (i pulsanti) all'interno della cella
                    icons = operations_cell.find_elements(By.CSS_SELECTOR,
                                                          "div.file-operations span.uranus-icon-cursor-pointer")
                    if len(icons) >= 2:
                        download_button = icons[1]  # il secondo span contiene l'icona di download
                        wait.until(EC.element_to_be_clickable((By.XPATH, ".//*")))
                        download_button.click()
                        if idx == 0:
                            print("Cliccato sul download del secondo file.")
                        else:
                            print("Cliccato sul download del primo file.")
                    else:
                        print(f"Download icon non trovato nella riga {2 - idx}.")
                except Exception as e:
                    print(f"Errore nel cliccare il download sulla riga {2 - idx}: {e}")
                time.sleep(2)

        # Attende ulteriori secondi per completare eventuali download
        time.sleep(60)
        print("Nomi dei file estratti:", file_names)
        return file_names[0:2]

    finally:
        driver.quit()


if __name__ == "__main__":
    extracted_file_names = main()
    print("I nomi dei file restituiti da main() sono:")
    for name in extracted_file_names:
        print(name)

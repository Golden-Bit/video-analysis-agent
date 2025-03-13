import os
import re
import time
import random
from selenium import webdriver
from selenium.webdriver.edge.service import Service as EdgeService
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from selenium.webdriver import ActionChains, Keys

################################################################################
# CONFIGURAZIONE E SUPPORTO
################################################################################

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

# URL diretto alla pagina "Media" del progetto/organizzazione specifica
MEDIA_URL = (
    "https://fh.dji.com/organization/"
    "c7172441-3df9-4e5b-85d8-97c985893b7c/"
    "project/b577be18-d159-459f-ada8-76a0dd08b3b8#/media"
)

################################################################################
# FUNZIONI DI UTILITÀ
################################################################################

def sanitize_folder_name(folder_name: str) -> str:
    """
    Rimuove i caratteri vietati da un nome di directory (Windows).
    Rimuove i seguenti caratteri: < > : " / \ | ? * ( )
    """
    folder_name_clean = re.sub(r'[<>:"/\\|?*()]', '', folder_name)
    return folder_name_clean.strip()


################################################################################
# LOGIN E GESTIONE SESSIONE
################################################################################

def start_session() -> (webdriver.Edge, WebDriverWait):
    """
    Avvia la sessione del browser Microsoft Edge e si autentica su DJI FlightHub (nella prima scheda).
    Ritorna sia il driver Selenium che l'oggetto WebDriverWait, così da poterli
    riutilizzare per fare download in una (o più) schede successive.

    In questo approccio, la scheda di login (prima scheda) resta aperta per tutta
    la durata; non si chiude.
    """

    # Impostazioni base di Edge
    options = webdriver.EdgeOptions()
    prefs = {
        "download.prompt_for_download": False,  # Non richiede conferma per il download
        "download.directory_upgrade": True,
        "safebrowsing.enabled": True            # Abilita Safe Browsing
    }
    options.add_experimental_option("prefs", prefs)
    #options.add_argument("--headless=new")
    options.add_argument("--start-maximized")  # Aggiungi questo argomento per avviare in full screen

    # Percorso del msedgedriver (personalizzare se necessario)
    edge_driver_path = r"app/AUTO_FLYGHTHUB/drivers/edge/msedgedriver.exe"
    service = EdgeService(executable_path=edge_driver_path)

    driver = webdriver.Edge(service=service, options=options)
    driver.maximize_window()
    wait = WebDriverWait(driver, 90)  # Timeout per le attese esplicite

    # (1) Carica la pagina di login
    driver.get(LOGIN_URL)
    time.sleep(3)

    # (1a) Clic sul banner dei cookie ("Required Only") se presente
    try:
        cookie_button = wait.until(
            EC.element_to_be_clickable(
                (By.CSS_SELECTOR, "button.cc-consent-require-only.cc-btn.cc-btn-default")
            )
        )
        cookie_button.click()
        time.sleep(1)
    except Exception:
        print("[Info] Banner dei cookie non presente o già gestito.")

    # (2) Inserimento username e password
    email_input = driver.find_element(By.NAME, "username")
    email_input.clear()
    email_input.send_keys(USERNAME)

    password_input = driver.find_element(By.CSS_SELECTOR, "input[aria-label='Password']")
    password_input.clear()
    password_input.send_keys(PASSWORD)

    login_button = driver.find_element(By.CSS_SELECTOR, "button[data-usagetag='login_button']")
    login_button.click()

    # (3) Clic su "enter-icon" per entrare nel progetto
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

    print("[Info] Login completato e primo progetto caricato nella prima scheda.")
    return driver, wait


################################################################################
# FUNZIONE PER DOWNLOAD SENZA CHIUDERE LA SCHEDA
################################################################################

def download_assets_in_same_tab(
    driver: webdriver.Edge,
    wait: WebDriverWait,
    plan_name: str = "MyTestPlan",
    date: str = "",
    time_str: str = "",
    directory_name: str = "",
    allowed_extensions: list = None,
    suffix_filter: str = ""
) -> list:
    """
    Riutilizza (o crea se non esiste) una seconda scheda di browser per eseguire i download.
    Non la chiude al termine, così da poterla riutilizzare nuovamente per chiamate successive.

    FLUSSO:
      1. Se la seconda scheda non esiste ancora, la crea.
      2. Passa alla scheda dedicata ai download e naviga su MEDIA_URL.
      3. Clicca "All Files" per resettare la vista.
      4. Costruisce la stringa di ricerca (search_query).
      5. Esegue la ricerca e clicca sulla cartella corrispondente.
      6. Crea la cartella locale (in base al nome reale della cartella sul web).
      7. Scarica i file che rispettano le estensioni e il suffix_filter (se impostato).
      8. Non chiude la scheda, rimane lì pronta per ulteriori download.

    PARAMETRI:
      - plan_name, date, time_str, directory_name: definiscono la stringa di ricerca
      - allowed_extensions: se None -> usa un default (mp4, avi, mov, mkv, jpg, jpeg, png, gif)
      - suffix_filter: stringa che, se non vuota, filtra i file che terminano con tale suffisso (case-insensitive).

    Ritorna la lista dei path completi dei file scaricati.
    """

    # Se l'utente non fornisce una lista di estensioni, usiamo un default
    if allowed_extensions is None:
        allowed_extensions = ['mp4', 'avi', 'mov', 'mkv', 'jpg', 'jpeg', 'png', 'gif']

    # 1) Se esiste solo una scheda (quella di login), creiamo la seconda scheda.
    #    Altrimenti la riutilizziamo.
    if len(driver.window_handles) == 1:
        driver.execute_script("window.open('');")
        print("[Info] Creata la seconda scheda per i download.")
    else:
        print("[Info] Riutilizzo la scheda secondaria già aperta.")

    # 2) Passo alla scheda secondaria (index 1, se ci sono 2 schede totali)
    driver.switch_to.window(driver.window_handles[1])
    driver.get(MEDIA_URL)

    # 3) Provo a cliccare su "All Files" per tornare sempre alla root
    try:
        all_files_breadcrumb = wait.until(
            EC.element_to_be_clickable((
                By.XPATH, "//span[@class='disk-app-ant-breadcrumb-link']//span[text()='All Files']"
            ))
        )
        all_files_breadcrumb.click()
        print('[Info] Cliccato su "All Files" con successo.')
    except Exception as e:
        print(f"[Warning] Impossibile cliccare su 'All Files': {e}")

    # 4) Costruzione della stringa di ricerca
    if directory_name:
        search_query = directory_name
    else:
        search_query = plan_name
        if date:
            search_query += " " + date
            if time_str:
                search_query += " " + time_str

    # Inserimento stringa di ricerca
    search_input = wait.until(
        EC.presence_of_element_located((
            By.CSS_SELECTOR,
            "span.search.uranus-custom-input.uranus-custom-input-light.disk-app-ant-input-affix-wrapper.disk-app-ant-input-affix-wrapper-lg input"
        ))
    )
    search_input.clear()
    search_input.send_keys(search_query)
    time.sleep(3)  # Attendi l'aggiornamento della lista

    # Trova la cartella corrispondente
    first_folder_element = wait.until(
        EC.element_to_be_clickable((
            By.XPATH,
            "(//div[@class='name-tag-container']//span[contains(@class, 'uranus-ellipsis-span') "
            f"and contains(text(), '{search_query}')])[1]"
        ))
    )

    # Nome effettivo della cartella
    actual_folder_name = first_folder_element.text.strip()
    actual_folder_name = sanitize_folder_name(actual_folder_name)

    # 5) Clicchiamo la cartella
    first_folder_element.click()
    print(f"[Info] Cliccato sul nome della cartella: {actual_folder_name}")

    # 6) Crea la directory di download in base al nome della cartella
    download_dir = os.path.join(os.getcwd(), "FH_DATA", actual_folder_name)
    if not os.path.exists(download_dir):
        os.makedirs(download_dir)

    # Aggiorniamo la directory di download
    driver.execute_cdp_cmd("Page.setDownloadBehavior", {
        "behavior": "allow",
        "downloadPath": download_dir
    })

    # 7) Attesa del caricamento dei file
    list_container = wait.until(
        EC.presence_of_element_located((By.CSS_SELECTOR, "div.document-content"))
    )
    time.sleep(3)

    # Estensioni e suffix
    suffix_filter_lower = suffix_filter.lower().strip()
    downloaded_file_names = []

    # Recupero file
    file_rows = driver.find_elements(
        By.XPATH,
        "//div[contains(@class, 'document-content')]//table[contains(@class, 'vxe-table--body')]//tbody//tr"
    )

    # Filtriamo i file validi
    candidate_rows = []
    for row in file_rows:
        try:
            name_element = row.find_element(
                By.CSS_SELECTOR,
                "div.name-tag-container div.file-name span.uranus-ellipsis-span"
            )
            file_name = name_element.text.strip()
            if file_name:
                ext = file_name.split('.')[-1].lower()
                if ext in allowed_extensions:
                    # Se suffix_filter è vuoto, non filtriamo
                    # Altrimenti, scarichiamo solo se il nome finisce col suffisso
                    if suffix_filter_lower == "" or file_name.lower().endswith(suffix_filter_lower + f".{ext}"):
                        candidate_rows.append(row)
        except Exception as e:
            print(f"[Errore] Non riesco a estrarre il nome del file: {e}")

    if not candidate_rows:
        print("[Info] Nessun file valido (estensione o suffix) trovato per il download.")
    else:
        # Invertiamo l'ordine (dal basso verso l'alto) per evitare overlay di popup
        candidate_rows = list(reversed(candidate_rows))

        for row in candidate_rows:
            file_name = "Sconosciuto"
            try:
                name_element = row.find_element(
                    By.CSS_SELECTOR,
                    "div.name-tag-container div.file-name span.uranus-ellipsis-span"
                )
                file_name = name_element.text.strip()

                operations_cell = row.find_element(By.CSS_SELECTOR, "td.vxe-body--column.col_9")
                icons = operations_cell.find_elements(
                    By.CSS_SELECTOR,
                    "div.file-operations span.uranus-icon-cursor-pointer"
                )
                if len(icons) >= 2:
                    # Presumiamo che il 2° pulsante sia "Download"
                    download_button = icons[1]
                    wait.until(EC.element_to_be_clickable((By.XPATH, ".//*")))
                    download_button.click()
                    time.sleep(3)

                    # Click "fuori" per chiudere l'overlay
                    rand_x = 50
                    rand_y = 0
                    ActionChains(driver).move_by_offset(rand_x, rand_y).click().perform()

                    # Subito dopo il click o dopo il blocco di ActionChains:
                    ActionChains(driver).send_keys(Keys.ESCAPE).perform()
                    time.sleep(1)

                    downloaded_file_names.append(file_name)
                    print(f"[Download] Cliccato il download per: {file_name}")
                else:
                    print(f"[Warning] Icona di download non trovata per: {file_name}")
            except Exception as e:
                print(f"[Error] Problema nel download di {file_name}: {e}")

            # Pausa tra un download e l'altro
            time.sleep(2)

    # Attendi il completamento del download (regolabile a seconda delle dimensioni)
    time.sleep(100)
    print("[Info] Download completato in cartella:", download_dir)
    print("[Info] File scaricati:", downloaded_file_names)

    # 8) NON chiudiamo la scheda (rimaniamo su quest'ultima).
    #    Eventualmente, se si vuole riportare il focus alla scheda login (handle[0]):
    #    driver.switch_to.window(driver.window_handles[0])

    # Ritorno la lista di path completi
    downloaded_paths = [os.path.join(download_dir, fname) for fname in downloaded_file_names]
    return downloaded_paths


################################################################################
# MAIN DI ESEMPIO
################################################################################

if __name__ == "__main__":
    """
    ESEMPIO DI UTILIZZO:

    1) Avvio la sessione e faccio login (start_session) -> Ritorna driver, wait
    2) Invoco download_assets_in_same_tab(...) con i parametri desiderati
    3) Ogni volta uso la *stessa* seconda scheda, e non la chiudo.
    4) Al termine, quando non mi serve più, chiudo l'intero browser con driver.quit().
    """

    # 1) Avvio e login
    driver, wait = start_session()

    # 2) Primo download
    extracted_files_1 = download_assets_in_same_tab(
        driver,
        wait,
        plan_name="Il Notturno - Perimetro",
        date="",
        allowed_extensions=["mp4", "mov", "jpg", "jpeg"],
        suffix_filter=""
    )
    print("PRIMO DOWNLOAD - File scaricati:", extracted_files_1)

    # 3) Secondo download (stessa scheda, SENZA aprirne un'altra e SENZA chiuderla)
    extracted_files_2 = download_assets_in_same_tab(
        driver,
        wait,
        plan_name="Untitled Plan",
        date="",
        allowed_extensions=["mp4", "mov", "jpg", "jpeg"],
        suffix_filter="T"
    )
    print("SECONDO DOWNLOAD - File scaricati:", extracted_files_2)

    # 4) Quando finito, chiudere il driver intero (tutte le schede)
    driver.quit()

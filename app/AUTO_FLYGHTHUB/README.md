## 1. Prerequisiti

- **Python installato:** Assicurati di avere Python (versione 3.7 o superiore) installato sul tuo sistema.  
  - **Windows:** [Scarica Python](https://www.python.org/downloads/windows/)  
  - **Linux:** Solitamente Python è preinstallato; altrimenti, installalo tramite il package manager della tua distribuzione (es. `sudo apt install python3` per Ubuntu/Debian).

- **Google Chrome installato:** Assicurati di avere l’ultima versione di Google Chrome installata.  
  - **Windows:** Scaricalo dal sito ufficiale [Google Chrome](https://www.google.com/chrome/).  
  - **Linux:** Puoi installarlo tramite il package manager oppure scaricare il pacchetto `.deb` o `.rpm` dal sito ufficiale.

---

## 2. Installare il pacchetto Selenium

Apri il prompt dei comandi (su Windows) o il terminale (su Linux) ed esegui:

```bash
pip install selenium
```

Verifica l’installazione con:

```bash
pip show selenium
```

---

## 3. Scaricare ChromeDriver

Selenium necessita di un driver per interagire con il browser Chrome. ChromeDriver è il driver ufficiale per Google Chrome.

### Passaggi comuni per Windows e Linux:

1. **Controlla la versione di Chrome:**  
   Apri Chrome e vai su `chrome://settings/help` (o `chrome://version` in alcune versioni) per visualizzare la versione del browser.

2. **Scarica la versione compatibile di ChromeDriver:**  
   Visita il sito [ChromeDriver - WebDriver for Chrome](https://sites.google.com/chromium.org/driver/) e scarica la versione di ChromeDriver compatibile con la tua versione di Chrome.

3. **Estrai ChromeDriver:**  
   - **Windows:** Estrai il file `chromedriver.exe` in una cartella a tua scelta.  
     _Suggerimento:_ Puoi aggiungere la cartella contenente `chromedriver.exe` alla variabile d'ambiente `PATH` oppure specificare il percorso completo nello script Python.
   - **Linux:** Estrai il file `chromedriver` (senza estensione `.exe`) e posizionalo in una cartella, ad esempio `/usr/local/bin` oppure in una cartella a tua scelta.  
     _Suggerimento:_ Se lo posizioni in `/usr/local/bin`, assicurati che la cartella sia presente nel PATH; in alternativa, specifica il percorso completo nello script.

---

## 4. Configurare e testare Selenium con Chrome

Crea un file Python, ad esempio `test_selenium.py`, e inserisci il seguente codice:

```python
from selenium import webdriver
from selenium.webdriver.chrome.service import Service
from selenium.webdriver.common.by import By
import time

# Specifica il percorso del ChromeDriver se non è stato aggiunto al PATH
# Su Windows, ad esempio:
# chrome_driver_path = r"C:\percorso\alla\cartella\chromedriver.exe"
# Su Linux, ad esempio:
# chrome_driver_path = "/percorso/alla/cartella/chromedriver"
chrome_driver_path = r"/percorso/alla/cartella/chromedriver"  # Modifica questo percorso in base al sistema

# Imposta il servizio per ChromeDriver
service = Service(executable_path=chrome_driver_path)

# Configura le opzioni per Chrome (opzionale)
options = webdriver.ChromeOptions()
options.add_argument("--start-maximized")  # Avvia Chrome in modalità schermo intero

# Inizializza il browser
driver = webdriver.Chrome(service=service, options=options)

# Apri una pagina web
driver.get("https://www.google.com")

# Esempio: cerca un elemento e interagisci con esso
try:
    # Trova la casella di ricerca di Google
    search_box = driver.find_element(By.NAME, "q")
    # Inserisci un testo nella casella di ricerca
    search_box.send_keys("Selenium Python guida")
    # Attendi un momento (opzionale)
    time.sleep(1)
    # Invia la ricerca (premi invio)
    search_box.submit()
    
    # Attendi il caricamento della pagina dei risultati
    time.sleep(3)
    
    # Stampa il titolo della pagina
    print("Titolo della pagina:", driver.title)
    
finally:
    # Chiudi il browser
    driver.quit()
```

### Spiegazione del codice:
- **Import delle librerie:**  
  Importiamo le classi necessarie da Selenium, come `webdriver`, `Service` e `By`.

- **Specificare il percorso di ChromeDriver:**  
  Se ChromeDriver non è presente nel `PATH`, specifica il percorso completo del file. Modifica la variabile `chrome_driver_path` in base al tuo sistema (Windows o Linux).

- **Configurazione del Service e delle opzioni:**  
  Creiamo un oggetto `Service` per ChromeDriver e impostiamo alcune opzioni (ad esempio, l’avvio a schermo intero).

- **Inizializzazione del browser e navigazione:**  
  Avviamo il browser e andiamo su Google. Utilizziamo Selenium per trovare la casella di ricerca (`By.NAME, "q"`), inserire del testo e inviare la ricerca.

- **Gestione del tempo e chiusura:**  
  Utilizziamo `time.sleep()` per attendere il caricamento della pagina (nota: in progetti reali potresti utilizzare *explicit waits* o *implicit waits* per una gestione migliore dei tempi) e infine chiudiamo il browser con `driver.quit()`.

---

## 5. Eseguire lo script

### Su Windows:
1. Apri il prompt dei comandi o PowerShell.
2. Naviga fino alla cartella contenente il file `test_selenium.py`.
3. Esegui il comando:
   ```bash
   python test_selenium.py
   ```

### Su Linux:
1. Apri il terminale.
2. Naviga nella directory contenente `test_selenium.py`:
   ```bash
   cd /percorso/della/cartella
   ```
3. Esegui lo script:
   ```bash
   python3 test_selenium.py
   ```

Se tutto è configurato correttamente, vedrai il browser Chrome aprirsi, eseguire la ricerca su Google e successivamente chiudersi. Nel terminale verrà stampato il titolo della pagina dei risultati.

---

## 6. Suggerimenti aggiuntivi

- **Gestione delle attese:**  
  Invece di utilizzare `time.sleep()`, puoi usare:
  - **Implicit Wait:**  
    ```python
    driver.implicitly_wait(10)  # Attende fino a 10 secondi per trovare un elemento
    ```
  - **Explicit Wait:**  
    ```python
    from selenium.webdriver.support.ui import WebDriverWait
    from selenium.webdriver.support import expected_conditions as EC

    wait = WebDriverWait(driver, 10)
    element = wait.until(EC.presence_of_element_located((By.NAME, "q")))
    ```

- **Utilizzare Virtual Environment:**  
  È buona pratica creare un ambiente virtuale per isolare le dipendenze del progetto.
  - **Windows:**
    ```bash
    python -m venv mio_ambiente
    mio_ambiente\Scripts\activate
    pip install selenium
    ```
  - **Linux:**
    ```bash
    python3 -m venv mio_ambiente
    source mio_ambiente/bin/activate
    pip install selenium
    ```

- **Gestione delle versioni:**  
  Assicurati che la versione di ChromeDriver corrisponda alla versione di Chrome installata. In caso di aggiornamenti del browser, potrebbe essere necessario aggiornare ChromeDriver.

import os
import re
import time
import random
import base64
import uuid
import tempfile
from typing import List, Optional
import json

import numpy as np
import cv2
import streamlit as st
import streamlit.components.v1 as components

# LangChain e AI
from langchain_openai import ChatOpenAI
from langchain.schema.messages import SystemMessage, HumanMessage
from langchain_core.messages import AIMessage

############################################
# IMPORTA LE FUNZIONI DEL NUOVO SCRIPT:
#   1) start_session()
#   2) download_assets_in_same_tab()
# Esempio:
#   from GET_STORED_FILES import start_session, download_assets_in_same_tab
############################################
from AUTO_FLYGHTHUB.GET_FH_DATA_EDGE import start_session, download_assets_in_same_tab


# Se non esiste, inizializziamo un contenitore di log
if "logs" not in st.session_state:
    st.session_state.logs = ""

# Se non esiste, inizializziamo la struttura per salvare i risultati
# Qui memorizzeremo ogni “blocco” di analisi concluso
if "analysis_results" not in st.session_state:
    st.session_state.analysis_results = []

################################################################################
# CONFIGURAZIONE LLM
################################################################################
BASE_SYSTEM_PROMPT = """
Sei un agente di videosorveglianza specializzato nell’analisi visiva di frame ripresi da un drone che sorvola un’area industriale, un perimetro o un complesso di edifici per finalità di videosorveglianza. Il tuo scopo è agire come un vero agente di sicurezza, monitorando eventuali anomalie, persone, veicoli o attività sospette.

Ad ogni chiamata riceverai:
- Un nuovo frame (sotto forma di immagine in base64).
- La cronologia dei frame precedenti, con le relative descrizioni già emesse.

**Comportamento atteso**:
1. **Descrivi il frame dal punto di vista della sicurezza**, individuando:
   - Numero e posizione approssimativa di **persone** o **veicoli** (camion, auto, droni esterni, ecc.).
   - Integrità delle infrastrutture di sicurezza (recinzioni, porte, cancelli, reti, torri di guardia, segnaletica di pericolo).
   - Potenziali situazioni di rischio o di comportamento anomalo (persone non autorizzate, movimenti sospetti, mezzi fuori luogo).
   - Cambiamenti rispetto ai frame precedenti (nuovi soggetti, veicoli spostati, ingressi lasciati aperti, ecc.).
   - **Se i frame provengono da una telecamera termica**:
     - Evidenzia possibili **fonti di calore anomalo** che potrebbero indicare un principio di incendio o un malfunzionamento di macchinari.
     - Segnala eventuali **variazioni di temperatura** sospette in prossimità di sostanze o aree sensibili (serbatoi, impianti di stoccaggio, tubazioni).
     - Monitora la presenza di **vapori o emissioni** inconsuete (ad esempio, fughe di gas caldi, fumi anomali) che potrebbero essere rilevate nella banda termica.
     - Annota differenze termiche che potrebbero suggerire **attività non autorizzate** o la presenza di persone in zone teoricamente vuote.
2. **Escludi dettagli non pertinenti alla sorveglianza** e non fornire analisi mediche. Concentrati su ciò che un vero agente di sicurezza vorrebbe sapere per prendere decisioni o allertare le forze di vigilanza.
3. La **descrizione** del frame va racchiusa tra questi marker, così da poterla estrarre automaticamente:

<attribute=frame_description| {"descrizione_frame": "..."} | attribute=frame_description>

4. Alla fine dell’analisi di tutti i frame, produci una **descrizione conclusiva del video**, che:
   - Riassuma i principali eventi e punti critici osservati nell’intera sequenza (numero totale di persone e/o veicoli visti, eventuali momenti di potenziale violazione della sicurezza, varchi lasciati incustoditi, ecc.).
   - Indichi eventuali raccomandazioni o richieste di intervento (se emergono situazioni d’allarme). In caso di **riprese termiche**, specifica se hai individuato zone potenzialmente pericolose (surriscaldamenti, fughe di gas, picchi di temperatura anomale).
   - Sia racchiusa tra i marker seguenti, così da poter essere estratta:

<attribute=final_description| {"descrizione_finale": "..."} | attribute=final_description>


5. **ANOMALIE**: Se rilevi anomalie (ad es. movimenti sospetti, presenza non autorizzata o altri eventi critici), includi un blocco aggiuntivo nella descrizione finale che riporti tutte le anomalie rilevate. Questo blocco deve essere racchiuso tra i seguenti tag:
   
   <attribute=anomaly| [{"anomaly": "descrizione anomalia 1"}, {"anomaly": "descrizione anomalia 2"}, ...] | attribute=anomaly>

   Se non vengono rilevate anomalie, non includere il blocco.
   
   Dovrai generare tale tag solo nella descrizione finale dei frame. e dovrai racchiudere in tale messaggio tra i tag tutte le anomalie rilevate. 
   Dovrai generare un solo tag descrizione ed eventualmente un solo tag di anomalie per ciascun messaggio di output generato. 
   Se non sono rilevate anomalie allora dovria generare solo il tag di descriizone.
   Se stai analizzando un video, allora dovrai associare dei timestamp alle anomalie rilevate, indicandoli all interno del testo del campo 'anomaly' nei json generati.

6. **Stile di descrizione**:
   - **SINTETICO**: Breve ed essenziale.
   - **NORMALE**: Lunghezza moderata, con dettaglio intermedio.
   - **DETTAGLIATO**: Più lungo e minuzioso.
   
7. Se l’utente fornisce richieste aggiuntive, integrale mantenendo lo stile desiderato.

Ricorda: **Non ripetere** le descrizioni dei frame precedenti, ma fanne tesoro per dare continuità e coerenza alle osservazioni.
"""

def get_length_instruction(length_style: str) -> str:
    if length_style.lower() == "sintetico":
        return "Scegli uno stile SINTETICO: descrizione breve ed essenziale."
    elif length_style.lower() == "normale":
        return "Scegli uno stile NORMALE: descrizione di lunghezza media e dettaglio moderato."
    elif length_style.lower() == "dettagliato":
        return "Scegli uno stile DETTAGLIATO: descrizione più lunga, ricca di particolari."
    else:
        return "Scegli uno stile NORMALE."

def get_system_prompt(length_style: str) -> str:
    length_instruction = get_length_instruction(length_style)
    return BASE_SYSTEM_PROMPT + "\n" + length_instruction

OPENAI_API_KEY = "..."
chat = ChatOpenAI(model="gpt-4o", temperature=0.25, max_tokens=2048, openai_api_key=OPENAI_API_KEY)


################################################################################
# FUNZIONI DI ESTRAZIONE FRAME / ANALISI
################################################################################
def decode_base64_video(video_base64: str) -> str:
    video_data = base64.b64decode(video_base64)
    tmp_dir = tempfile.mkdtemp()
    video_path = os.path.join(tmp_dir, f"{uuid.uuid4()}.mp4")
    with open(video_path, "wb") as f:
        f.write(video_data)
    return video_path

def extract_frames(video_path: str, width: int, height: int,
                   num_frames: Optional[int] = None,
                   frame_rate: Optional[int] = None) -> List[str]:
    cap = cv2.VideoCapture(video_path)
    total_frames = int(cap.get(cv2.CAP_PROP_FRAME_COUNT))
    fps = cap.get(cv2.CAP_PROP_FPS)

    if num_frames is not None and num_frames > 0:
        frame_indices = [int(i * total_frames / num_frames) for i in range(num_frames)]
    elif frame_rate is not None and frame_rate > 0:
        frame_step = int(fps / frame_rate) if frame_rate <= fps else 1
        frame_indices = list(range(0, total_frames, frame_step))
    else:
        # Default: 5 frame
        num_frames = 5
        frame_indices = [int(i * total_frames / num_frames) for i in range(num_frames)]

    frame_paths = []
    for i, idx in enumerate(frame_indices):
        cap.set(cv2.CAP_PROP_POS_FRAMES, idx)
        ret, frame = cap.read()
        if not ret:
            break
        resized_frame = cv2.resize(frame, (width, height), interpolation=cv2.INTER_AREA)
        tmp_dir = tempfile.mkdtemp()
        frame_path = os.path.join(tmp_dir, f"frame_{i}.jpg")
        cv2.imwrite(frame_path, resized_frame)
        frame_paths.append(frame_path)
    cap.release()
    return frame_paths

def image_to_base64(image_path: str) -> str:
    with open(image_path, "rb") as f:
        return "data:image/jpeg;base64," + base64.b64encode(f.read()).decode("utf-8")


######################
# ANALISI IMMAGINI
######################
def analyze_image_generator(
    image_data: bytes,
    width: int,
    height: int,
    length_style: str,
    additional_request: str
):



    # Carica (o inizializza) il contatore dei frame
    counter_file = os.path.join(os.getcwd(), "app/frame_counter.json")
    if os.path.exists(counter_file):
        with open(counter_file, "r", encoding="utf-8") as f:
            counter_data = json.load(f)
    else:
        # Imposta il contatore iniziale e il massimo; ad esempio, MAX_FRAMES = 100
        counter_data = {"CONTATORE": 0, "MAX_FRAMES": 20}
        with open(counter_file, "w", encoding="utf-8") as f:
            json.dump(counter_data, f)

    # Se il contatore ha già raggiunto il massimo, interrompi l'analisi
    if counter_data["CONTATORE"] >= counter_data["MAX_FRAMES"]:
        yield "Numero massimo di frame raggiunto. Analisi non eseguita."
        return

    # Ricarica il contatore all'inizio di ogni iterazione (in caso di aggiornamenti esterni)
    with open(counter_file, "r", encoding="utf-8") as f:
        counter_data = json.load(f)
    if counter_data["CONTATORE"] >= counter_data["MAX_FRAMES"]:
        yield "Numero massimo di frame raggiunto. Interrompo l'analisi dei frame."
        return



    yield "Analisi dell'immagine..."
    nparr = np.frombuffer(image_data, np.uint8)
    img = cv2.imdecode(nparr, cv2.IMREAD_COLOR)
    if img is None:
        yield "Errore nel decodificare l'immagine."
        raise ValueError("Impossibile decodificare l'immagine.")
    resized_img = cv2.resize(img, (width, height), interpolation=cv2.INTER_AREA)
    tmp_dir = tempfile.mkdtemp()
    image_path = os.path.join(tmp_dir, f"{uuid.uuid4()}.jpg")
    cv2.imwrite(image_path, resized_img)
    img_b64 = image_to_base64(image_path)

    system_prompt = get_system_prompt(length_style)
    system_message = SystemMessage(content=system_prompt)
    messages = [system_message]

    additional_req_text = ""
    if additional_request.strip():
        additional_req_text = f"Richieste aggiuntive: {additional_request.strip()}"

    image_user_text = "Analizza l'immagine seguente."
    image_user_text += f"\nStile: {length_style.upper()}"
    if additional_req_text:
        image_user_text += f"\n{additional_req_text}"

    human_content = [
        {"type": "text", "text": image_user_text},
        {"type": "image_url", "image_url": {"url": img_b64, "detail": "auto"}}
    ]
    human_message = HumanMessage(content=human_content)
    response = chat(messages + [human_message])
    ai_response = response.content

    start_tag = "<attribute=frame_description|"
    end_tag = "| attribute=frame_description>"
    start_idx = ai_response.find(start_tag)
    end_idx = ai_response.find(end_tag)
    if start_idx == -1 or end_idx == -1:
        yield "Errore nella formattazione della risposta del modello per l'immagine."
        raise ValueError("Formato non corretto nella risposta del modello per l'immagine.")
    json_str = ai_response[start_idx + len(start_tag):end_idx].strip()

    try:
        desc_dict = json.loads(json_str)
        image_description = desc_dict.get("descrizione_frame", "")



        # Dopo aver elaborato il frame, incrementa il contatore e salva il file
        counter_data["CONTATORE"] += 1
        with open(counter_file, "w", encoding="utf-8") as f:
            json.dump(counter_data, f)



    except:
        yield "Errore nel parsing del JSON per la descrizione dell'immagine."
        raise ValueError("Errore nel parsing del JSON per l'immagine.")

    yield f"Descrizione immagine: {image_description}"
    yield f"Descrizione finale dell'immagine: {image_description}"

    # Dopo aver ottenuto 'final_text' e prima del return, aggiungi:
    anomaly_start_tag = "<attribute=anomaly|"
    anomaly_end_tag = "| attribute=anomaly>"
    anomaly_start_idx = ai_response.find(anomaly_start_tag)
    anomaly_end_idx = ai_response.find(anomaly_end_tag)
    anomaly_text = None
    if anomaly_start_idx != -1 and anomaly_end_idx != -1:
        anomaly_json_str = ai_response[anomaly_start_idx + len(anomaly_start_tag):anomaly_end_idx].strip()
        try:
            #anomaly_dict = json.loads(anomaly_json_str)
            anomaly_text = str(anomaly_json_str)  # json.dump(anomaly_dict, indent=2)

        except Exception as e:
            yield "Errore nel parsing del JSON per l'anomalia."
            raise ValueError("Errore nel parsing del JSON per l'anomalia.")
    if anomaly_text:
        yield f"Anomalia: {anomaly_text}"

    return [image_description], image_description


######################
# ANALISI VIDEO
######################
def analyze_video_generator(
    video_data: bytes,
    num_frames: Optional[int],
    frame_rate: Optional[int],
    width: int,
    height: int,
    length_style: str,
    additional_request: str
):




    # Carica (o inizializza) il contatore dei frame
    counter_file = os.path.join(os.getcwd(), "app/frame_counter.json")
    if os.path.exists(counter_file):
        with open(counter_file, "r", encoding="utf-8") as f:
            counter_data = json.load(f)
    else:
        # Imposta il contatore iniziale e il massimo; ad esempio, MAX_FRAMES = 100
        counter_data = {"CONTATORE": 0, "MAX_FRAMES": 20}
        with open(counter_file, "w", encoding="utf-8") as f:
            json.dump(counter_data, f)

    # Se il contatore ha già raggiunto il massimo, interrompi l'analisi
    if counter_data["CONTATORE"] >= counter_data["MAX_FRAMES"]:
        yield "Numero massimo di frame raggiunto. Analisi non eseguita."
        return



    yield "Decodifica del video..."
    video_base64 = base64.b64encode(video_data).decode('utf-8')
    video_path = decode_base64_video(video_base64)
    yield "Estrazione dei frame..."
    frame_paths = extract_frames(
        video_path,
        width=width,
        height=height,
        num_frames=num_frames if frame_rate == 0 else None,
        frame_rate=frame_rate if frame_rate > 0 else None
    )
    yield f"{len(frame_paths)} frame estratti."

    system_prompt = get_system_prompt(length_style)
    system_message = SystemMessage(content=system_prompt)
    messages = [system_message]
    frame_descriptions = []

    additional_req_text = ""
    if additional_request.strip():
        additional_req_text = f"Richieste aggiuntive: {additional_request.strip()}"

    cap = cv2.VideoCapture(video_path)
    fps = cap.get(cv2.CAP_PROP_FPS)
    total_frames = int(cap.get(cv2.CAP_PROP_FRAME_COUNT))
    cap.release()

    for i, frame_path in enumerate(frame_paths):

        # Ricarica il contatore all'inizio di ogni iterazione (in caso di aggiornamenti esterni)
        with open(counter_file, "r", encoding="utf-8") as f:
            counter_data = json.load(f)
        if counter_data["CONTATORE"] >= counter_data["MAX_FRAMES"]:
            yield "Numero massimo di frame raggiunto. Interrompo l'analisi dei frame."
            return

        yield f"Analisi del frame {i + 1}/{len(frame_paths)}..."
        # Calcolo indice e timestamp
        if num_frames and num_frames > 0:
            original_index = int(i * total_frames / num_frames)
        elif frame_rate and frame_rate > 0:
            frame_step = int(fps / frame_rate) if frame_rate <= fps else 1
            original_index = i * frame_step
        else:
            original_index = i

        timestamp_seconds = original_index / fps if fps > 0 else 0
        hh = int(timestamp_seconds // 3600)
        mm = int((timestamp_seconds % 3600) // 60)
        ss = int(timestamp_seconds % 60)
        timestamp_str = f"{hh:02d}:{mm:02d}:{ss:02d}"

        frame_b64 = image_to_base64(frame_path)
        prev_descs_limited = frame_descriptions[-100:]
        frame_user_text = (f"Timestamp: {timestamp_str} - Analizza il frame seguente. "
                           "Tieni conto delle descrizioni precedenti. "
                           "IMPORTANTE: menziona eventuali riferimenti a timestamp in descrizione se ci sono eventi.")
        frame_user_text += f"\nStile: {length_style.upper()}"
        if additional_req_text:
            frame_user_text += f"\n{additional_req_text}"

        human_content = [{"type": "text", "text": frame_user_text}]
        for idx, d in enumerate(prev_descs_limited):
            human_content.append({"type": "text", "text": f"Descrizione frame precedente {idx + 1}: {d}"})
        human_content.append({"type": "image_url", "image_url": {"url": frame_b64, "detail": "auto"}})

        human_message = HumanMessage(content=human_content)
        response = chat(messages + [human_message])
        ai_response = response.content

        start_tag = "<attribute=frame_description|"
        end_tag = "| attribute=frame_description>"
        start_idx = ai_response.find(start_tag)
        end_idx = ai_response.find(end_tag)
        if start_idx == -1 or end_idx == -1:
            yield "Errore nella formattazione della risposta del modello per il frame."
            raise ValueError("Formato non corretto nella risposta del modello.")
        json_str = ai_response[start_idx + len(start_tag):end_idx].strip()

        try:
            desc_dict = json.loads(json_str)
            desc_frame = desc_dict.get("descrizione_frame", "")


            # Dopo aver elaborato il frame, incrementa il contatore e salva il file
            counter_data["CONTATORE"] += 1
            with open(counter_file, "w", encoding="utf-8") as f:
                json.dump(counter_data, f)


        except:
            yield "Errore nel parsing del JSON per la descrizione del frame."
            raise ValueError("Errore nel parsing del JSON per il frame.")

        frame_descriptions.append(desc_frame)
        messages.append(human_message)
        messages.append(AIMessage(content=ai_response))
        yield f"Descrizione frame {i + 1}: {desc_frame}"

    yield "Generazione descrizione finale del video..."
    final_user_text = ("Genera la descrizione finale del video basandoti sulle descrizioni dei frame precedenti. "
                       "IMPORTANTE: menziona i timestamp se ci sono stati eventi rilevanti.\n")
    final_user_text += f"Stile: {length_style.upper()}"
    if additional_req_text:
        final_user_text += f"\n{additional_req_text}"
    final_user_text += "\nFornisci la descrizione finale racchiusa nei tag richiesti."

    final_human_content = [{"type": "text", "text": final_user_text}]
    for idx, d in enumerate(frame_descriptions):
        final_human_content.append({"type": "text", "text": f"Descrizione frame {idx + 1}: {d}"})
    final_human_message = HumanMessage(content=final_human_content)
    final_response = chat(messages + [final_human_message])
    final_text = final_response.content

    final_start_tag = "<attribute=final_description|"
    final_end_tag = "| attribute=final_description>"
    fs_idx = final_text.find(final_start_tag)
    fe_idx = final_text.find(final_end_tag)
    if fs_idx == -1 or fe_idx == -1:
        yield "Errore nella formattazione della descrizione finale."
        raise ValueError("La risposta del modello non contiene la descrizione finale formattata correttamente.")
    final_json_str = final_text[fs_idx + len(final_start_tag):fe_idx].strip()
    try:
        final_desc_dict = json.loads(final_json_str)
        final_description = final_desc_dict.get("descrizione_finale", "")


        # Dopo aver elaborato il frame, incrementa il contatore e salva il file
        counter_data["CONTATORE"] += 1
        with open(counter_file, "w", encoding="utf-8") as f:
            json.dump(counter_data, f)


    except:
        yield "Errore nel parsing del JSON per la descrizione finale."
        raise ValueError("Errore nel parsing del JSON per la descrizione finale.")

    yield f"Descrizione finale del video: {final_description}"


    # Dopo aver ottenuto 'final_text' e prima del return, aggiungi:
    anomaly_start_tag = "<attribute=anomaly|"
    anomaly_end_tag = "| attribute=anomaly>"
    anomaly_start_idx = final_text.find(anomaly_start_tag)
    anomaly_end_idx = final_text.find(anomaly_end_tag)
    anomaly_text = None
    if anomaly_start_idx != -1 and anomaly_end_idx != -1:
        anomaly_json_str = final_text[anomaly_start_idx + len(anomaly_start_tag):anomaly_end_idx].strip()
        try:
            #anomaly_dict = json.loads(anomaly_json_str)
            anomaly_text = str(anomaly_json_str)  # json.dump(anomaly_dict, indent=2)
        except Exception as e:
            yield "Errore nel parsing del JSON per l'anomalia."
            raise ValueError("Errore nel parsing del JSON per l'anomalia.")
    if anomaly_text:
        yield f"Anomalia: {anomaly_text}"
    return frame_descriptions, final_description


################################################################################
# STREAMLIT UI
################################################################################

st.title("Analisi Video/Immagini da Pianificazione DJI (Sessione Unica)")

if "driver" not in st.session_state or "wait" not in st.session_state:
    st.markdown("### Effettua Login su DJI FlightHub")

    # --------------------------------------
    # (1) AGGIUNGI I DUE CAMPI PER USERNAME/PASSWORD
    # --------------------------------------
    username_input = st.text_input(
        "Inserisci Username",
        value="",
        placeholder="Se vuoto, uso quello di default"
    )
    password_input = st.text_input(
        "Inserisci Password",
        value="",
        placeholder="Se vuoto, uso quella di default",
        type="password"
    )

    # --------------------------------------
    # (2) PULSANTE CHE SCATENA IL LOGIN
    # --------------------------------------
    login_btn = st.button("Esegui Login e Avvia Sessione Selenium")

    if login_btn:
        # Se l'utente non inserisce nulla, usiamo i valori di default
        if not username_input.strip():
            username_input = "xr01.theia@gmail.com"
        if not password_input.strip():
            password_input = "LBFL2hFxFwUTKc5"


        with st.spinner("Avvio sessione e login su DJI..."):
            try:
                # PASSIAMO username e password A start_session
                driver, wait = start_session(username=username_input, password=password_input)
                st.session_state.driver = driver
                st.session_state.wait = wait
                st.success("Login e sessione avviati con successo!")
            except Exception as e:
                st.error(f"Errore durante la creazione della sessione: {e}")
else:
    st.success("Sessione già avviata (sei loggato su DJI FlightHub).")

# STEP 2: Se la sessione è attiva, mostriamo i parametri di download e analisi
if "driver" in st.session_state and "wait" in st.session_state:
    st.markdown("## Parametri di Download e Analisi")

    # Parametri di "cosa" scaricare (piano, data, orario, directory, etc.)
    use_directory = st.checkbox("Usa directory personalizzata", value=False)
    if use_directory:
        directory_name = st.text_input("Nome directory", value="DefaultDirectory")
    else:
        directory_name = ""

    use_flight_plan = st.checkbox("Usa piano di volo personalizzato", value=False)
    if use_flight_plan:
        flight_plan = st.text_input("Nome del piano di volo", value="MyTestPlan")
    else:
        flight_plan = "MyTestPlan"

    use_date = st.checkbox("Usa data personalizzata", value=False)
    if use_date:
        year = st.number_input("Anno", min_value=2000, max_value=2100, value=2023)
        month = st.number_input("Mese", min_value=1, max_value=12, value=1)
        day = st.number_input("Giorno", min_value=1, max_value=31, value=1)
        date_str = f"{year:04d}-{month:02d}-{day:02d}"
    else:
        date_str = ""

    use_time = st.checkbox("Usa orario personalizzato", value=False)
    if use_time:
        hour = st.number_input("Ora", min_value=0, max_value=23, value=12)
        minute = st.number_input("Minuti", min_value=0, max_value=59, value=0)
        time_str = f"{hour:02d}:{minute:02d}"
    else:
        time_str = ""

    # Nuovi parametri per filtri file

    # Filtro per estensioni: abilita un campo per inserire una lista di estensioni separate da virgola
    use_extension_filter = st.checkbox("Filtra per estensioni specifiche", value=False)
    if use_extension_filter:
        extensions_input = st.text_input("Inserisci estensioni (separate da virgola)", value="mp4,avi,mov,mkv,jpg,jpeg,png,gif")
        # Converte l'input in una lista di stringhe, eliminando spazi extra
        allowed_extensions = [ext.strip().lower() for ext in extensions_input.split(",") if ext.strip() != ""]
    else:
        allowed_extensions = None  # Il download_assets_in_same_tab utilizzerà il default se None

    # Filtro per suffisso: abilita un campo per inserire il suffisso da filtrare
    use_suffix_filter = st.checkbox("Filtra per suffisso", value=False)
    if use_suffix_filter:
        suffix_filter = st.text_input("Inserisci il suffisso da filtrare", value="")
    else:
        suffix_filter = ""

    # Nuovo parametro per abilitare/disabilitare la sovrascrittura dei file di analisi
    enable_overwrite = st.checkbox("Abilita sovrascrittura analisi", value=True)

    # Aggiunta checkbox per la ricorrenza
    use_recurring = st.checkbox("Abilita ricorrenza (ripeti analisi periodicamente)?", value=False)
    recurring_minutes = 0
    if use_recurring:
        # Campo per scegliere ogni quanti minuti ripetere
        recurring_minutes = st.number_input("Intervallo (minuti) per la ricorrenza",
                                           min_value=1, max_value=1440, value=5)

    # Parametri di analisi
    num_frames = st.number_input("Numero di frame (se frame_rate=0)", min_value=1, value=5)
    frame_rate = st.number_input("Frame rate di estrazione (0 => usa num_frames)", min_value=0, value=0)
    width = st.number_input("Larghezza frame ridimensionato", min_value=32, value=256)
    height = st.number_input("Altezza frame ridimensionato", min_value=32, value=256)
    length_style = st.selectbox("Stile descrizione:", ("sintetico", "normale", "dettagliato"), index=1)
    additional_request = st.text_area("Richieste aggiuntive (opzionale):", "")

    # ---------------------------
    # FUNZIONE PER ESEGUIRE UNA SOLA ANALISI
    # ---------------------------
    def run_analysis_once():
        st.write("**Avvio procedura di download...**")
        try:
            # Richiamiamo la funzione che si appoggia alla stessa sessione,
            # ma in una SECONDA scheda riutilizzabile
            downloaded_file_names = download_assets_in_same_tab(
                driver=st.session_state.driver,
                wait=st.session_state.wait,
                plan_name=flight_plan,
                date=date_str,
                time_str=time_str,
                directory_name=directory_name,
                allowed_extensions=allowed_extensions,  # usa il valore dall'input (o default se None)
                suffix_filter=suffix_filter             # usa il suffisso impostato dall'utente
            )
            st.success("Download completato!")
            if downloaded_file_names:
            #    st.write("File scaricati (path completi):")
            #    for f in downloaded_file_names:
            #        st.write(f)
                pass
            else:
                st.warning("Nessun file scaricato. Forse la directory era vuota o non trovata.")
        except Exception as e:
            st.error(f"Errore in fase di download: {e}")
            st.stop()

        # Se abbiamo scaricato almeno un file, cerchiamo di capire il "nome cartella" da usare
        folder_name = "Sconosciuta"
        if downloaded_file_names:
            first_file = downloaded_file_names[0]
            folder_path = os.path.dirname(first_file)  # cartella
            folder_name = os.path.basename(folder_path)  # ultima parte del path

        # Filtra i file in base a estensione (video / immagini)
        def is_video_file(fname: str) -> bool:
            return fname.split(".")[-1].lower() in ["mp4", "avi", "mov", "mkv"]
        def is_image_file(fname: str) -> bool:
            return fname.split(".")[-1].lower() in ["jpg", "jpeg", "png", "gif"]

        video_files = [f for f in downloaded_file_names if is_video_file(f)]
        image_files = [f for f in downloaded_file_names if is_image_file(f)]

        # Se non ci sono file, fermiamoci
        if not video_files and not image_files:
            st.warning("Nessun file immagine o video trovato per l'analisi.")
            st.stop()

        # Ora facciamo l'analisi e salviamo i risultati in una struttura
        video_results = []
        image_results = []

        # Analisi Video
        for video_file in video_files:

            # Controlla se esiste già il file di analisi per questo video
            output_folder = os.path.dirname(video_file)
            anomalies_folder = os.path.join(output_folder, "ANOMALIE")
            video_basename = os.path.basename(video_file)
            anomaly_filename = os.path.join(anomalies_folder, f"anomaly_{video_basename}.txt")

            # Se la sovrascrittura è disabilitata ed il file esiste, salta l'analisi per questo file
            if not enable_overwrite and os.path.exists(anomaly_filename):
                st.info(f"Analisi per {video_basename} già esistente. Salto l'analisi.")
                continue

            st.session_state.logs = ""  # reset log per questo file
            frame_desc_list = []
            final_desc_text = ""
            anomaly_text = ""
            try:
                with open(video_file, "rb") as vf:
                    video_data = vf.read()
                gen = analyze_video_generator(
                    video_data=video_data,
                    num_frames=num_frames if frame_rate == 0 else None,
                    frame_rate=frame_rate if frame_rate > 0 else 0,
                    width=width,
                    height=height,
                    length_style=length_style,
                    additional_request=additional_request
                )

                for step_msg in gen:
                    st.session_state.logs += step_msg + "\n" + "-" * 100 + "\n"
                    if step_msg.startswith("Descrizione frame"):
                        frame_desc_list.append(step_msg)
                    elif step_msg.startswith("Descrizione finale del video:"):
                        final_desc_text = step_msg.replace("Descrizione finale del video: ", "")
                    elif step_msg.startswith("Anomalia:"):
                        anomaly_text = step_msg.replace("Anomalia: ", "")

            except Exception as e:
                st.session_state.logs += f"\n[Errore analisi video] {e}"

            # Se è stata rilevata un'anomalia, salvala in un file
            if anomaly_text and anomaly_text.strip():
                # Determina la cartella di output dell'analisi
                output_folder = os.path.dirname(video_file)
                anomalies_folder = os.path.join(output_folder, "ANOMALIE")
                if not os.path.exists(anomalies_folder):
                    os.makedirs(anomalies_folder)
                video_basename = os.path.basename(video_file)
                anomaly_filename = os.path.join(anomalies_folder, f"anomaly_{video_basename}.txt")

                try:
                    temp_anomaly_text = json.loads(anomaly_text)
                    temp_anomaly_text = json.dumps(temp_anomaly_text, indent=2)
                    anomaly_text = temp_anomaly_text
                except Exception as e:
                    print(f"[Error]: {e}")

                with open(anomaly_filename, "w", encoding="utf-8") as af:
                    af.write(anomaly_text)
                st.info(f"File di anomalia creato: {anomaly_filename}")


            # Salvataggio della descrizione finale in un file di testo
            if final_desc_text:
                output_folder = os.path.dirname(video_file)
                base_name = os.path.splitext(os.path.basename(video_file))[0]
                base_name = base_name.replace(".", "_")
                description_file = os.path.join(output_folder, f"{base_name}.txt")
                with open(description_file, "w", encoding="utf-8") as f:
                    f.write(final_desc_text)


            video_results.append({
                "file_path": video_file,
                "frame_desc_list": frame_desc_list,
                "final_desc_text": final_desc_text,
                "raw_logs": st.session_state.logs
            })

        # Analisi Immagini
        for image_file in image_files:

            # Controlla se esiste già il file di analisi per questa immagine
            output_folder = os.path.dirname(image_file)
            anomalies_folder = os.path.join(output_folder, "ANOMALIE")
            image_basename = os.path.basename(image_file)
            anomaly_filename = os.path.join(anomalies_folder, f"anomaly_{image_basename}.txt")

            if not enable_overwrite and os.path.exists(anomaly_filename):
                st.info(f"Analisi per {image_basename} già esistente. Salto l'analisi.")
                continue

            st.session_state.logs = ""  # reset log per questo file
            frame_desc_list = []
            final_desc_text = ""
            anomaly_text = ""
            try:
                with open(image_file, "rb") as f:
                    image_data = f.read()

                gen = analyze_image_generator(
                    image_data=image_data,
                    width=width,
                    height=height,
                    length_style=length_style,
                    additional_request=additional_request
                )
                for step_msg in gen:
                    st.session_state.logs += step_msg + "\n" + "-" * 100 + "\n"
                    if step_msg.startswith("Descrizione"):
                        frame_desc_list.append(step_msg)
                    elif step_msg.startswith("Anomalia:"):
                        anomaly_text = step_msg.replace("Anomalia: ", "")

                if frame_desc_list:
                    final_desc_text = frame_desc_list[-1]  # ultima come "descrizione finale"
            except Exception as e:
                st.session_state.logs += f"\n[Errore analisi immagine] {e}"



            # Salvataggio della descrizione finale in un file di testo
            if final_desc_text:
                output_folder = os.path.dirname(image_file)
                base_name = os.path.splitext(os.path.basename(image_file))[0]
                base_name = base_name.replace(".", "_")
                description_file = os.path.join(output_folder, f"{base_name}.txt")
                with open(description_file, "w", encoding="utf-8") as f:
                    f.write(final_desc_text)



            image_results.append({
                "file_path": image_file,
                "frame_desc_list": frame_desc_list,
                "final_desc_text": final_desc_text,
                "raw_logs": st.session_state.logs
            })

            # Se è stata rilevata un'anomalia, salvala in un file
            if anomaly_text and anomaly_text.strip():
                # Otteniamo la cartella di output a partire dal path dell'immagine
                output_folder = os.path.dirname(image_file)
                anomalies_folder = os.path.join(output_folder, "ANOMALIE")
                if not os.path.exists(anomalies_folder):
                    os.makedirs(anomalies_folder)
                image_basename = os.path.basename(image_file)
                anomaly_filename = os.path.join(anomalies_folder, f"anomaly_{image_basename}.txt")

                try:
                    temp_anomaly_text = json.loads(anomaly_text)
                    temp_anomaly_text = json.dumps(temp_anomaly_text, indent=2)
                    anomaly_text = temp_anomaly_text
                except Exception as e:
                    print(f"[Error]: {e}")

                with open(anomaly_filename, "w", encoding="utf-8") as af:
                    af.write(anomaly_text)
                st.info(f"File di anomalia creato: {anomaly_filename}")

        # Aggiungiamo i risultati in testa alla lista delle analysis
        new_analysis_block = {
            "folder_name": folder_name,
            "video_results": video_results,
            "image_results": image_results
        }
        # mettiamo in cima (index 0) per visualizzarlo come primo
        st.session_state.analysis_results.insert(0, new_analysis_block)


    if st.button("Scarica & Analizza con Parametri Correnti"):
        if use_recurring and recurring_minutes > 0:
            # Calcoliamo l'intervallo in secondi
            run_interval = recurring_minutes * 60


            # Definiamo una funzione che verrà eseguita periodicamente
            @st.fragment(run_every=run_interval)
            def periodic_analysis():
                run_analysis_once()
                st.info(f"Analisi completata. (Aggiornamento ogni {recurring_minutes} minuti)")
                #st.rerun()

            # Avviamo il fragment
            periodic_analysis()
        else:
            # Modalità di esecuzione singola
            run_analysis_once()

# --- AREA DI VISUALIZZAZIONE RISULTATI (tutti i blocchi salvati) ---
#st.markdown("## Risultati (Storico delle Analisi)")
@st.fragment(run_every=60)
def update_results():
    # Iteriamo su st.session_state.analysis_results in ordine
    # (la più recente in alto, le vecchie in basso)
    for i, analysis_block in enumerate(st.session_state.analysis_results):
        folder_label = analysis_block["folder_name"]
        # Expander con la cartella
        with st.expander(f"Analisi n° {i + 1} - Cartella: {folder_label}", expanded=False):
            # Elenco file video
            for vinfo in analysis_block["video_results"]:
                video_file = vinfo["file_path"]
                frame_desc_list = vinfo["frame_desc_list"]
                final_desc = vinfo["final_desc_text"]
                raw_logs = vinfo["raw_logs"]

                with st.container(border=True):
                    st.markdown(f"**{os.path.basename(video_file)}**")
                    st.video(video_file)
                    st.subheader("Descrizioni Frame:")
                    for desc in frame_desc_list:
                        st.write(desc)
                    if final_desc:
                        st.subheader("Descrizione Finale:")
                        st.write(final_desc)


                    # Estrai e mostra le anomalie in giallo (se presenti) dal log
                    raw_log_lines = raw_logs#.split("<br>")
                    if "Anomalia:" in raw_log_lines:
                        print(raw_log_lines)
                        anomalies = [raw_log_lines.split("Anomalia:")[-1]] #[line for line in raw_log_lines if line.strip().startswith("Anomalia:")]
                        print(anomalies)
                    else:
                        anomalies = ""

                    if anomalies:
                        st.subheader("Anomalie:")
                        for anomaly in anomalies:
                            st.markdown(f"<p style='color:yellow; font-weight:bold;'>{anomaly}</p>",
                                        unsafe_allow_html=True)

                    st.subheader("Log di Analisi:")
                    st.markdown(f"""
                    <div style='color:white;background-color:black;height:200px;overflow-y:auto;padding:5px;' id='video_log_{video_file}'>
                      {raw_logs}
                    </div>
                    """, unsafe_allow_html=True)


            # Elenco file immagini
            for iinfo in analysis_block["image_results"]:
                image_file = iinfo["file_path"]
                frame_desc_list = iinfo["frame_desc_list"]
                final_desc = iinfo["final_desc_text"]
                raw_logs = iinfo["raw_logs"]

                with st.container(border=True):
                    st.markdown(f"**{os.path.basename(image_file)}**")
                    st.image(image_file)
                    st.subheader("Descrizioni:")
                    for d in frame_desc_list:
                        st.write(d)
                    if final_desc:
                        st.subheader("Descrizione Finale:")
                        st.write(final_desc)

                    raw_log_lines = raw_logs#.split("<br>")
                    if "Anomalia:" in raw_log_lines:
                        print(raw_log_lines)
                        anomalies = [raw_log_lines.split("Anomalia:")[-1]] #[line for line in raw_log_lines if line.strip().startswith("Anomalia:")]
                        print(anomalies)
                    else:
                        anomalies = ""
                    if anomalies:
                        st.subheader("Anomalie:")
                        for anomaly in anomalies:
                            st.markdown(f"<p style='color:yellow; font-weight:bold;'>{anomaly}</p>",
                                        unsafe_allow_html=True)

                    st.subheader("Log di Analisi:")
                    st.markdown(f"""
                    <div style='color:white;background-color:black;height:200px;overflow-y:auto;padding:5px;' id='img_log_{image_file}'>
                      {raw_logs}
                    </div>
                    """, unsafe_allow_html=True)


# Richiama il fragment per attivare l'aggiornamento periodico dei risultati
update_results()


# Ultimo bottone per chiudere il browser (logout)
st.markdown("---")
if "driver" in st.session_state and st.button("Chiudi l'intero browser (logout)"):
    try:
        st.session_state.driver.quit()
        del st.session_state["driver"]
        del st.session_state["wait"]
        st.success("Browser chiuso e sessione terminata.")
    except:
        st.warning("Sessione già chiusa o non più valida.")

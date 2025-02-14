import base64
import os
import uuid
import tempfile
from typing import List, Optional
import json
import cv2
import time
from io import BytesIO
from PIL import Image

import streamlit as st

from langchain_openai import ChatOpenAI
from langchain.schema.messages import SystemMessage, HumanMessage
from langchain_core.messages import AIMessage

# IMPORTA la funzione main dello script Selenium che esegue il download dei file
from AUTO_FLYGHTHUB.get_stored_file import main as selenium_main

# ----------------------------
# CONFIGURAZIONE DEL MODELLO LLM
# ----------------------------
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
   - Indichi eventuali raccomandazioni o richieste di intervento (se emergono situazioni d’allarme). In caso di **riprese termiche**, specifica se hai individuato zone potenzialmente pericolose (surriscaldamenti, fughe di gas, picchi di temperatura anomali).
   - Sia racchiusa tra i marker seguenti, così da poter essere estratta:

<attribute=final_description| {"descrizione_finale": "..."} | attribute=final_description>

5. **Stile di descrizione**:
   - **SINTETICO**: Breve ed essenziale, evidenziando solo i punti chiave della sorveglianza.
   - **NORMALE**: Lunghezza moderata, con un livello di dettaglio intermedio.
   - **DETTAGLIATO**: Più lungo e minuzioso, ma sempre mirato alla sicurezza e al monitoraggio.

6. Se l’utente fornisce richieste aggiuntive (ad esempio “Evidenzia se qualcuno supera un confine proibito” o “Segnala perdite di calore inconsuete”), integrale mantenendo lo stile desiderato. Evita riferimenti diagnostici (nessuna valutazione medica) o altri contenuti non correlati alla sicurezza.

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


# ----------------------------
# FUNZIONI DI ANALISI VIDEO
# ----------------------------
def decode_base64_video(video_base64: str) -> str:
    video_data = base64.b64decode(video_base64)
    tmp_dir = tempfile.mkdtemp()
    video_path = os.path.join(tmp_dir, f"{uuid.uuid4()}.mp4")
    with open(video_path, "wb") as f:
        f.write(video_data)
    return video_path


def extract_frames(video_path: str, width: int, height: int, num_frames: Optional[int] = None,
                   frame_rate: Optional[int] = None) -> List[str]:
    cap = cv2.VideoCapture(video_path)
    total_frames = int(cap.get(cv2.CAP_PROP_FRAME_COUNT))
    fps = cap.get(cv2.CAP_PROP_FPS)

    if num_frames is not None:
        frame_indices = [int(i * total_frames / num_frames) for i in range(num_frames)]
    elif frame_rate is not None:
        frame_step = int(fps / frame_rate) if frame_rate <= fps else 1
        frame_indices = list(range(0, total_frames, frame_step))
    else:
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


def analyze_video_generator(video_data: bytes, num_frames: Optional[int], frame_rate: Optional[int],
                            width: int, height: int, length_style: str, additional_request: str):
    yield "Decodifica del video..."
    video_base64 = base64.b64encode(video_data).decode('utf-8')
    video_path = decode_base64_video(video_base64)

    yield "Estrazione dei frame..."
    frame_paths = extract_frames(video_path, width=width, height=height, num_frames=num_frames, frame_rate=frame_rate)
    yield f"{len(frame_paths)} frame estratti."

    system_prompt = get_system_prompt(length_style)
    system_message = SystemMessage(content=system_prompt)
    messages = [system_message]
    frame_descriptions = []

    additional_req_text = ""
    if additional_request.strip():
        additional_req_text = f"Richieste aggiuntive: {additional_request.strip()}"

    for i, frame_path in enumerate(frame_paths):
        yield f"Analisi del frame {i + 1}/{len(frame_paths)}..."
        frame_b64 = image_to_base64(frame_path)

        previous_descriptions_limited = frame_descriptions[-100:]

        frame_user_text = "Analizza il frame seguente. Tieni conto delle descrizioni precedenti. Non analisi mediche."
        frame_user_text += f"\nStile: {length_style.upper()}"
        if additional_req_text:
            frame_user_text += f"\n{additional_req_text}"

        human_content = [{"type": "text", "text": frame_user_text}]
        for idx, desc in enumerate(previous_descriptions_limited):
            human_content.append({"type": "text", "text": f"Descrizione frame precedente {idx + 1}: {desc}"})
        human_content.append({"type": "image_url", "image_url": {"url": frame_b64, "detail": "auto"}})

        human_message = HumanMessage(content=human_content)

        while True:
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
                break
            except:
                yield "Errore nel parsing del JSON per la descrizione del frame."
                raise ValueError("Errore nel parsing del JSON per la descrizione del frame.")

        frame_descriptions.append(desc_frame)
        messages.append(human_message)
        messages.append(AIMessage(content=ai_response))
        yield f"Descrizione frame {i + 1}: {desc_frame}"

    yield "Generazione descrizione finale del video..."
    final_user_text = "Genera la descrizione finale del video basandoti sulle descrizioni dei frame precedenti. Non analisi mediche, ma solo qualitative ed estetiche."
    final_user_text += f"\nStile: {length_style.upper()}"
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
    except:
        yield "Errore nel parsing del JSON per la descrizione finale."
        raise ValueError("Errore nel parsing del JSON per la descrizione finale.")

    yield f"Descrizione finale del video: {final_description}"
    return frame_descriptions, final_description


# ----------------------------
# CONFIGURAZIONE DEL MODELLO CHATOPENAI
# ----------------------------
OPENAI_API_KEY = "|$$$$$|"
chat = ChatOpenAI(model="gpt-4o", temperature=0.25, max_tokens=2048, openai_api_key=OPENAI_API_KEY)

# ----------------------------
# STREAMLIT UI
# ----------------------------
st.title("Analisi Video da Piano di Volo DJI")

with st.form(key="analysis_form"):
    flight_plan = st.text_input("Inserisci il nome del piano di volo", value="MyTestPlan")
    num_frames = st.number_input("Numero di frame da estrarre (usa num_frames se frame_rate = 0)", min_value=1, value=5)
    frame_rate = st.number_input("Frame rate di estrazione (0 per ignorare e usare num_frames)", min_value=0, value=0)
    width = st.number_input("Larghezza frame ridimensionato", min_value=32, value=256)
    height = st.number_input("Altezza frame ridimensionato", min_value=32, value=256)
    length_style = st.selectbox(
        "Seleziona lo stile della descrizione",
        ("sintetico", "normale", "dettagliato"),
        index=1  # di default "normale"
    )
    additional_request = st.text_area("Richieste aggiuntive (opzionale):", "")
    start_button = st.form_submit_button("Avvia Analisi")

# Se frame_rate è 0, usiamo num_frames; altrimenti frame_rate
actual_num_frames = None if frame_rate > 0 else num_frames
actual_frame_rate = frame_rate if frame_rate > 0 else None

log_area = st.empty()  # Placeholder per i log
if "logs" not in st.session_state:
    st.session_state.logs = ""

if start_button:
    # 1. Esecuzione dello script Selenium per scaricare i file dal piano di volo
    with st.spinner("Esecuzione script Selenium per scaricare i video dal piano di volo..."):
        try:
            # La funzione selenium_main riceve il nome del piano di volo e restituisce i nomi dei file scaricati
            downloaded_file_names = selenium_main(plan_name=flight_plan)
        except Exception as e:
            st.error(f"Errore durante l'esecuzione dello script Selenium: {e}")
            st.stop()

    st.success("Download completato!")
    st.write("File scaricati: " + ", ".join(downloaded_file_names))

    # 2. Caricamento del primo file MP4 dalla cartella Downloads di Windows
    try:
        downloads_folder = os.path.join(os.environ["USERPROFILE"], "Downloads")
    except Exception as e:
        st.error(f"Impossibile determinare la cartella Downloads: {e}")
        st.stop()

    first_file = downloaded_file_names[0]
    video_file_path = os.path.join(downloads_folder, first_file)
    try:
        with open(video_file_path, "rb") as f:
            video_data = f.read()
    except Exception as e:
        st.error(f"Errore nel caricamento del file video '{first_file}': {e}")
        st.stop()

    # 3. Avvio dell'analisi video sul file caricato
    with st.spinner("Esecuzione analisi video..."):
        frame_desc_list = []
        final_desc_text = ""
        gen = analyze_video_generator(
            video_data, actual_num_frames, actual_frame_rate,
            width, height, length_style, additional_request
        )
        for step_log in gen:
            # Aggiorna i log in tempo reale
            st.session_state.logs += step_log + "\n" + "-" * 120 + "\n"
            log_area.text_area("Log del processo", st.session_state.logs, height=200)
            if step_log.startswith("Descrizione frame "):
                frame_desc_list.append(step_log)
            elif step_log.startswith("Descrizione finale del video:"):
                final_desc_text = step_log.replace("Descrizione finale del video: ", "")

    st.success("Analisi completata con successo!")
    st.subheader("Descrizioni dei Frame:")
    for d in frame_desc_list:
        st.write(d)
    if final_desc_text:
        st.subheader("Descrizione Finale del Video:")
        st.write(final_desc_text)

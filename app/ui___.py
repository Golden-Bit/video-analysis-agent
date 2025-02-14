import base64
import os
import uuid
import tempfile
from typing import List, Optional, Tuple
import json
import cv2
import time
from io import BytesIO
from PIL import Image
import threading

import streamlit as st

from langchain_openai import ChatOpenAI
from langchain.schema.messages import SystemMessage, HumanMessage
from langchain_core.messages import AIMessage

# IMPORTA la funzione Selenium per lo stream extraction da uno script esterno.
# In questo esempio la funzione è importata da AUTO_FLYGHTHUB.cockpit
from AUTO_FLYGHTHUB.cockpit import main as selenium_stream_main

# TODO:
#  - NON RESTITUIRE ERRORE SE NON SI PUò ELABORARE IMMAIGNE, MA GESTISCI LA RISPSOTA (EV.MODIFICA PROMPT)
#  - PERMETTI DI SELEZIONARE TRA VISIONE NORMALE E VISIONE A INFRAROSSI
#  - IN AUTOMAZIONE ACQUSIIZIONE, AUTOMATIZZA ANCHE LA FUORIUSCITA DEI DUE MENU CON PULSANTE 'OK'
#  - INTEGRA ANCHE LA LETTURA DELLA TEMPERATURA NELLE RISPOSTE DELL'AGENTE
# ---------------------------------
# CONFIGURAZIONE DEL MODELLO LLM
# ---------------------------------
BASE_SYSTEM_PROMPT = """
Sei un agente di videosorveglianza specializzato nell’analisi visiva di frame ripresi da un drone che sorvola un’area industriale, un perimetro o un complesso di edifici per finalità di sorveglianza. Il tuo obiettivo è quello di agire come un vero agente di sicurezza, monitorando eventuali anomalie, persone, veicoli o attività sospette.

Ad ogni chiamata riceverai:
- Un nuovo frame (sotto forma di immagine in base64).
- La cronologia dei frame precedenti, con le relative descrizioni già emesse.

**Comportamento atteso**:

1. **Descrivi il frame dal punto di vista della sicurezza**, tenendo conto anche del **tempo (minuto e secondo) del video** a cui appartiene. In particolare:
   - Riporta il **timestamp** (ad es. “00:15” o “01:05”) relativo al momento in cui è stato estratto il frame.
   - Indica numero e posizione approssimativa di persone o veicoli.
   - Valuta l’integrità delle infrastrutture di sicurezza e segnala eventuali situazioni anomale.
   - Evidenzia eventuali cambiamenti rispetto ai frame precedenti.
   - Se i frame provengono da una telecamera termica, sottolinea eventuali anomalie termiche.

2. **Escludi dettagli non pertinenti alla sorveglianza** (niente analisi mediche).

3. Per ogni frame, racchiudi la descrizione tra i seguenti marker, includendo anche il timestamp:
```
<attribute=frame_description| {"descrizione_frame": "...", "timestamp_frame": "..."} | attribute=frame_description>
```

4. Alla fine dell’analisi di tutti i frame, produci una **descrizione conclusiva del video** che riassuma gli eventi principali, associandoli ai relativi timestamp, e racchiudila tra i marker:
```
<attribute=final_description| {"descrizione_finale": "..."} | attribute=final_description>
```

5. **Stile di descrizione**:
   - **SINTETICO**: Testo conciso con i punti chiave.
   - **NORMALE**: Descrizione di lunghezza e dettaglio moderati.
   - **DETTAGLIATO**: Testo approfondito e ricco di particolari.

6. Se vengono fornite richieste aggiuntive, integrale nella descrizione.

Ricorda di non ripetere le descrizioni precedenti, ma usale come contesto per mantenere coerenza.
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

# ---------------------------------
# FUNZIONE DI UTILITÀ: Conversione immagine in base64
# ---------------------------------
def image_to_base64(image_path: str) -> str:
    with open(image_path, "rb") as f:
        return "data:image/jpeg;base64," + base64.b64encode(f.read()).decode("utf-8")

# ---------------------------------
# FUNZIONE: Estrazione frame da video (con timestamp)
# (Qui non usiamo una funzione di estrazione da video, poiché i frame vengono generati dallo script Selenium)
# ---------------------------------

# ---------------------------------
# GENERATORE PER ANALISI DELLO STREAM
# ---------------------------------
def analyze_stream_generator(width: int, height: int, length_style: str, additional_request: str):
    yield "Inizio analisi stream..."
    system_prompt = get_system_prompt(length_style)
    system_message = SystemMessage(content=system_prompt)
    messages = [system_message]
    frame_descriptions = []

    # Set per tenere traccia dei file già processati
    processed_files = set()
    # Specifica il percorso della cartella di output dei frame
    output_folder = "app/AUTO_FLYGHTHUB/OUTPUT_FRAMES"
    if not os.path.exists(output_folder):
        os.makedirs(output_folder)

    last_new_frame_time = time.time()

    while True:
        # Elenca i file PNG nella cartella OUTPUT_FRAMES (i frame hanno il nome "frame_<timestamp>.png")
        all_files = [f for f in os.listdir(output_folder) if f.startswith("frame_") and f.endswith(".png")]
        all_files.sort()  # Ordinati per nome (ossia per timestamp)

        new_files = [f for f in all_files if f not in processed_files]

        if new_files:
            last_new_frame_time = time.time()
            for file in new_files:
                processed_files.add(file)
                # Estrai il timestamp dal nome del file
                timestamp_str = file[len("frame_"):-len(".png")]
                try:
                    ts = int(timestamp_str)
                    minutes, seconds = divmod(int(ts / 1000), 60)
                    time_str = f"{minutes:02d}:{seconds:02d}"
                except:
                    time_str = "00:00"

                frame_path = os.path.join(output_folder, file)
                frame_b64 = image_to_base64(frame_path)

                # Costruisci il prompt per il frame (includendo il timestamp)
                frame_user_text = (
                    f"Analizza il frame seguente. Tieni conto delle descrizioni precedenti.\n"
                    f"Questo frame è stato estratto al tempo (mm:ss): {time_str}."
                )
                frame_user_text += f"\nStile: {length_style.upper()}"
                if additional_request.strip():
                    frame_user_text += f"\nRichieste aggiuntive: {additional_request.strip()}"

                human_content = [{"type": "text", "text": frame_user_text}]
                previous_descriptions = frame_descriptions[-100:]
                for idx, desc in enumerate(previous_descriptions):
                    human_content.append({"type": "text", "text": f"Descrizione frame precedente {idx + 1}: {desc}"})
                human_content.append({"type": "image_url", "image_url": {"url": frame_b64, "detail": "auto"}})

                human_message = HumanMessage(content=human_content)

                while True:
                    response = chat(messages + [human_message])
                    ai_response = response.content
                    # Estrazione della descrizione racchiusa tra i marker
                    start_tag = "<attribute=frame_description|"
                    end_tag = "| attribute=frame_description>"
                    start_idx = ai_response.find(start_tag)
                    end_idx = ai_response.find(end_tag)

                    if start_idx == -1 or end_idx == -1:
                        print(response)
                        yield "Errore nella formattazione della risposta del modello per il frame."
                        raise ValueError("Formato non corretto nella risposta del modello.")

                    json_str = ai_response[start_idx + len(start_tag):end_idx].strip()
                    try:
                        desc_dict = json.loads(json_str)
                        desc_frame = desc_dict.get("descrizione_frame", "")
                        # Se il timestamp non è incluso, lo aggiungiamo
                        if "timestamp_frame" not in desc_dict:
                            desc_frame = f"{desc_frame} [Timestamp: {time_str}]"
                        break
                    except:
                        yield "Errore nel parsing del JSON per la descrizione del frame."
                        raise ValueError("Errore nel parsing del JSON per la descrizione del frame.")

                frame_descriptions.append(desc_frame)
                messages.append(human_message)
                messages.append(AIMessage(content=ai_response))
                yield f"Descrizione frame per {file} (timestamp {time_str}): {desc_frame}"
        else:
            # Se non ci sono nuovi frame, controlla se sono passati più di 10 secondi
            if time.time() - last_new_frame_time > 10:
                yield "Nessun nuovo frame per 10 secondi. Interruzione analisi stream."
                break
        time.sleep(1)

    # Genera la descrizione finale del video
    yield "Generazione descrizione finale del video..."
    final_user_text = (
        "Genera la descrizione finale del video basandoti sulle descrizioni dei frame precedenti. "
        "Non analisi mediche, ma solo qualitative ed estetiche."
    )
    final_user_text += f"\nStile: {length_style.upper()}"
    if additional_request.strip():
        final_user_text += f"\nRichieste aggiuntive: {additional_request.strip()}"
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

# ---------------------------------
# CONFIGURAZIONE DEL MODELLO CHATOPENAI
# ---------------------------------
OPENAI_API_KEY = "|$$$$$|"
chat = ChatOpenAI(model="gpt-4o", temperature=0.25, max_tokens=2048, openai_api_key=OPENAI_API_KEY)

# ---------------------------------
# STREAMLIT UI
# ---------------------------------
st.title("Analisi Video da Stream – Estrazione di Frame e JSON")

with st.form(key="stream_analysis_form"):
    # L'input per il nome del piano di volo può essere omesso se non necessario
    # flight_plan = st.text_input("Inserisci il nome del piano di volo", value="MyTestPlan")
    width = st.number_input("Larghezza frame ridimensionato", min_value=32, value=256)
    height = st.number_input("Altezza frame ridimensionato", min_value=32, value=256)
    length_style = st.selectbox(
        "Seleziona lo stile della descrizione",
        ("sintetico", "normale", "dettagliato"),
        index=1  # di default "normale"
    )
    additional_request = st.text_area("Richieste aggiuntive (opzionale):", "")
    start_button = st.form_submit_button("Avvia Analisi")

log_area = st.empty()
if "logs" not in st.session_state:
    st.session_state.logs = ""

if start_button:
    # 1. Avvia lo script Selenium in background per estrarre frame e JSON dallo stream
    with st.spinner("Avvio Selenium in background per estrarre frame e JSON dallo stream..."):
        try:
            selenium_thread = threading.Thread(target=selenium_stream_main)
            selenium_thread.daemon = True
            selenium_thread.start()
        except Exception as e:
            st.error(f"Errore durante l'avvio dello script Selenium: {e}")
            st.stop()
    st.success("Script Selenium avviato in background. I frame saranno salvati nella cartella OUTPUT_FRAMES.")

    # 2. Avvia l'analisi dello stream, monitorando la cartella OUTPUT_FRAMES per nuovi frame
    with st.spinner("Analisi stream in corso..."):
        frame_desc_list = []
        final_desc_text = ""
        gen = analyze_stream_generator(width, height, length_style, additional_request)
        for step_log in gen:
            st.session_state.logs += step_log + "\n" + "-" * 120 + "\n"
            log_area.text_area("Log del processo", st.session_state.logs, height=200)
            if step_log.startswith("Descrizione frame"):
                frame_desc_list.append(step_log)
            elif step_log.startswith("Descrizione finale del video:"):
                final_desc_text = step_log.replace("Descrizione finale del video: ", "")
    st.success("Analisi stream completata con successo!")
    st.subheader("Descrizioni dei Frame:")
    for d in frame_desc_list:
        st.write(d)
    if final_desc_text:
        st.subheader("Descrizione Finale del Video:")
        st.write(final_desc_text)
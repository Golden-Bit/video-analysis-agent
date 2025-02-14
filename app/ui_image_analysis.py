import base64
import os
import uuid
import tempfile
from typing import Optional
import json
import cv2
from io import BytesIO
from PIL import Image

import streamlit as st

from langchain_openai import ChatOpenAI
from langchain.schema.messages import SystemMessage, HumanMessage
from langchain_core.messages import AIMessage

# Prompt di base per il modello. Verrà arricchito con le istruzioni sulla lunghezza dell'output.
BASE_SYSTEM_PROMPT = """
Sei un assistente virtuale specializzato nell'analisi visiva di immagini.
Ti verrà fornita una singola immagine (in base64).
Il tuo compito è:
1. Fornire una descrizione qualitativa dell'immagine, coerente con ciò che viene mostrato e che fornisca dettagli rilevanti dal punto di vista visivo, come se fosse un'analisi professionale dell'immagine, ma non medica e senza alcuna pretesa diagnostica.
2. La descrizione deve essere racchiusa tra i seguenti marker speciali, per consentirne il parsing:
<attribute=frame_description| {"descrizione_frame": "..."} | attribute=frame_description>

Non fornire interpretazioni mediche e non includere informazioni sensibili.
La descrizione deve essere esclusivamente qualitativa ed estetica.

Inoltre, adatta la lunghezza della descrizione in base alla seguente istruzione aggiuntiva:
- SINTETICO: Fornisci una descrizione breve, essenziale, minimalista.
- NORMALE: Fornisci una descrizione di lunghezza moderata e dettaglio medio.
- DETTAGLIATO: Fornisci una descrizione molto ricca di particolari, più lunga e minuziosa.

L'utente sceglierà tra "sintetico", "normale", "dettagliato".
Adatta il tuo output di conseguenza.
"""

OPENAI_API_KEY = "......"
chat = ChatOpenAI(model="gpt-4o", temperature=0.25, max_tokens=2048, openai_api_key=OPENAI_API_KEY)

def image_to_base64(image_data: bytes) -> str:
    return "data:image/jpeg;base64," + base64.b64encode(image_data).decode("utf-8")

def resize_image(image_data: bytes, width: int, height: int) -> bytes:
    # Carica l'immagine in PIL
    img = Image.open(BytesIO(image_data))
    img_resized = img.resize((width, height))
    # Converte l'immagine ridimensionata in bytes
    buf = BytesIO()
    img_resized.save(buf, format="JPEG")
    return buf.getvalue()

def generate_system_prompt(length_style: str) -> str:
    if length_style.lower() == "sintetico":
        length_instruction = "Scegli uno stile SINTETICO: descrizione breve ed essenziale."
    elif length_style.lower() == "normale":
        length_instruction = "Scegli uno stile NORMALE: descrizione di lunghezza media e dettaglio moderato."
    elif length_style.lower() == "dettagliato":
        length_instruction = "Scegli uno stile DETTAGLIATO: descrizione più lunga, ricca di particolari."
    else:
        length_instruction = "Scegli uno stile NORMALE."

    return BASE_SYSTEM_PROMPT + "\n" + length_instruction

def analyze_single_image(image_data: bytes, length_style: str, additional_request: str):
    # Genera il prompt di sistema in base allo stile desiderato
    system_prompt = generate_system_prompt(length_style)
    system_message = SystemMessage(content=system_prompt)
    messages = [system_message]

    # Converti l'immagine in base64
    image_b64 = image_to_base64(image_data)

    # Messaggio utente (human message) con richieste aggiuntive
    # Le richieste aggiuntive vengono concatenate alla frase base
    human_text = "Analizza l'immagine seguente. Non generare analisi mediche. Rispetta lo stile richiesto."
    if additional_request.strip():
        human_text += "\nRichieste aggiuntive: " + additional_request.strip()

    human_content = [
        {"type": "text", "text": human_text},
        {"type": "image_url", "image_url": {"url": image_b64, "detail": "auto"}}
    ]

    human_message = HumanMessage(content=human_content)

    response = chat(messages + [human_message])
    ai_response = response.content

    # Parsing della risposta
    start_tag = "<attribute=frame_description|"
    end_tag = "| attribute=frame_description>"
    start_idx = ai_response.find(start_tag)
    end_idx = ai_response.find(end_tag)

    if start_idx == -1 or end_idx == -1:
        raise ValueError("Formato non corretto nella risposta del modello.")

    json_str = ai_response[start_idx+len(start_tag):end_idx].strip()
    desc_dict = json.loads(json_str)
    desc_frame = desc_dict.get("descrizione_frame", "")
    return desc_frame

# ---------------------------------
# Streamlit UI
# ---------------------------------

st.title("Image Analysis with LLM - Richieste Aggiuntive")

with st.form(key="image_analysis_form"):
    uploaded_image = st.file_uploader("Carica un'immagine (JPG/PNG)", type=["jpg", "jpeg", "png"])
    width = st.number_input("Larghezza immagine ridimensionata", min_value=32, value=256)
    height = st.number_input("Altezza immagine ridimensionato", min_value=32, value=256)

    length_style = st.selectbox(
        "Seleziona lo stile della descrizione",
        ("sintetico", "normale", "dettagliato"),
        index=1
    )

    additional_request = st.text_area("Richieste aggiuntive (opzionale):", "")

    start_button = st.form_submit_button("Avvia Analisi")

log_container = st.container()
log_area = log_container.empty()  # Placeholder per un unico text_area aggiornabile

if start_button:
    if uploaded_image is None:
        st.error("Per favore carica un'immagine prima di avviare l'analisi.")
    else:
        image_data = uploaded_image.read()

        if 'logs' not in st.session_state:
            st.session_state.logs = ""

        st.session_state.logs = "Ridimensionamento dell'immagine...\n"
        log_area.text_area("Log del processo", st.session_state.logs, height=200)

        # Ridimensiona l'immagine
        resized_image_data = resize_image(image_data, width, height)
        st.session_state.logs += "Immagine ridimensionata con successo.\n"
        st.session_state.logs += "Analisi dell'immagine in corso...\n"
        log_area.text_area("Log del processo", st.session_state.logs, height=200)

        try:
            desc_frame = analyze_single_image(resized_image_data, length_style, additional_request)
            st.session_state.logs += "Analisi completata con successo!\n"
            st.session_state.logs += f"Descrizione immagine ({length_style}): {desc_frame}\n"
            log_area.text_area("Log del processo", st.session_state.logs, height=200)

            st.success("Analisi completata con successo!")
            st.subheader("Descrizione dell'Immagine:")
            st.write(desc_frame)

        except Exception as e:
            st.error(f"Errore nell'analisi: {e}")
            st.session_state.logs += f"Errore: {e}\n"
            log_area.text_area("Log del processo", st.session_state.logs, height=200)

import base64
import os
import uuid
import tempfile
from typing import List, Optional
from fastapi import FastAPI, Body
from pydantic import BaseModel
import cv2
from io import BytesIO
from PIL import Image
import json

from langchain_openai import ChatOpenAI
from langchain.schema.messages import SystemMessage, HumanMessage
from langchain_core.messages import AIMessage

app = FastAPI()

# Il prompt di sistema può essere definito all'inizio
SYSTEM_PROMPT = """
Sei un assistente virtuale specializzato nell'analisi visiva di frame estratti da un video. Ti verranno forniti dei frame sotto forma di immagini (in base64). 
Ad ogni chiamata ti verrà passato un nuovo frame insieme alla storia dei frame precedenti già descritti. Il tuo compito è:
1. Fornire una descrizione qualitativa del frame corrente, coerente con le immagini fornite e che fornisca dettagli rilevanti dal punto di vista visivo, come se fosse un'analisi professionale dell'immagine, ma non medica e senza alcuna pretesa diagnostica.
2. La descrizione deve essere racchiusa tra i seguenti marker speciali, per consentirne il parsing: 
<attribute=frame_description| {"descrizione_frame": "..."} | attribute=frame_description>

Dopo aver analizzato tutti i frame, dovrai fornire una descrizione finale del video. La descrizione finale sarà prodotta in un'ultima chiamata senza nuovi frame, basandoti sulle descrizioni dei singoli frame. Anche questa descrizione finale deve essere fornita racchiusa tra speciali marker:
<attribute=final_description| {"descrizione_finale": "..."} | attribute=final_description>

Ricorda: Ogni volta che analizzi un nuovo frame devi considerare la descrizione dei frame precedenti che ti verrà fornita come chat history. Non devi ripetere le descrizioni precedenti, ma devi tenerle in considerazione per mantenere coerenza nel tempo.

Nota: Le descrizioni devono essere esclusivamente qualitative, estetiche, non mediche, e non devono contenere informazioni sensibili. Devono essere analisi visive, non interpretazioni mediche.
"""

# Configurazione del modello
# Inserire la propria OpenAI API Key
#OPENAI_API_KEY = "..."

chat = ChatOpenAI(model="gpt-4o", temperature=0.25, max_tokens=2048, openai_api_key=OPENAI_API_KEY)

# Parametri di esempio: limite descrizioni precedenti incluse nella storia
MAX_PREVIOUS_DESCRIPTIONS = 100

class VideoRequest(BaseModel):
    video_base64: str
    num_frames: Optional[int] = None
    frame_rate: Optional[int] = None
    # Aggiungiamo i parametri width e height per il resize dei frame
    width: Optional[int] = 256
    height: Optional[int] = 256


def decode_base64_video(video_base64: str) -> str:
    """
    Decodifica il video base64 e lo salva in un file temporaneo.
    Restituisce il percorso del file video.
    """
    print("Decodifica del video in base64...")
    video_data = base64.b64decode(video_base64)
    tmp_dir = tempfile.mkdtemp()
    video_path = os.path.join(tmp_dir, f"{uuid.uuid4()}.mp4")
    with open(video_path, "wb") as f:
        f.write(video_data)
    print(f"Video salvato in: {video_path}")
    return video_path


def extract_frames(video_path: str, width: int, height: int, num_frames: Optional[int] = None, frame_rate: Optional[int] = None) -> List[str]:
    """
    Estrae i frame dal video.
    Se num_frames è fornito, estrae quel numero di frame uniformemente distribuiti sul video.
    Se frame_rate è fornito, estrae i frame a quell'intervallo.
    Inoltre, effettua il resize di ogni frame alla dimensione width x height.
    Restituisce una lista di percorsi dei frame estratti.
    """
    print("Estrazione dei frame dal video...")
    cap = cv2.VideoCapture(video_path)
    total_frames = int(cap.get(cv2.CAP_PROP_FRAME_COUNT))
    fps = cap.get(cv2.CAP_PROP_FPS)
    print(f"Frame totali nel video: {total_frames}, FPS: {fps}")

    if num_frames is not None:
        print(f"Estrazione di {num_frames} frame uniformemente distribuiti.")
        frame_indices = [int(i * total_frames / num_frames) for i in range(num_frames)]
    elif frame_rate is not None:
        print(f"Estrazione di frame con frame_rate: {frame_rate}")
        frame_step = int(fps / frame_rate) if frame_rate <= fps else 1
        frame_indices = list(range(0, total_frames, frame_step))
    else:
        print("Nessun parametro fornito, estraggo 5 frame di default.")
        num_frames = 5
        frame_indices = [int(i * total_frames / num_frames) for i in range(num_frames)]

    frame_paths = []
    for i, idx in enumerate(frame_indices):
        cap.set(cv2.CAP_PROP_POS_FRAMES, idx)
        ret, frame = cap.read()
        if not ret:
            print(f"Impossibile leggere il frame all'indice {idx}. Stop.")
            break

        # Effettuiamo il resize del frame
        resized_frame = cv2.resize(frame, (width, height), interpolation=cv2.INTER_AREA)

        tmp_dir = tempfile.mkdtemp()
        frame_path = os.path.join(tmp_dir, f"frame_{i}.jpg")
        cv2.imwrite(frame_path, resized_frame)
        frame_paths.append(frame_path)
        print(f"Frame {i} estratto, ridimensionato a {width}x{height} e salvato in: {frame_path}")

    cap.release()
    print("Estrazione frame completata.")
    return frame_paths


def image_to_base64(image_path: str) -> str:
    with open(image_path, "rb") as f:
        return "data:image/jpeg;base64," + base64.b64encode(f.read()).decode("utf-8")


@app.post("/analyze_video")
def analyze_video(req: VideoRequest):
    print("Ricevuta richiesta di analisi video.")
    # Decodifica del video
    video_path = decode_base64_video(req.video_base64)

    # Estrazione dei frame con resize a width x height
    frame_paths = extract_frames(
        video_path,
        width=req.width,
        height=req.height,
        num_frames=req.num_frames,
        frame_rate=req.frame_rate
    )

    print("Inizializzazione della conversazione con il modello...")
    system_message = SystemMessage(content=SYSTEM_PROMPT)
    messages = [system_message]

    # Manteniamo una lista di descrizioni dei frame precedenti
    frame_descriptions = []

    # Per ogni frame estratto, chiediamo una descrizione
    for i, frame_path in enumerate(frame_paths):
        print(f"\nAnalisi del frame {i+1} di {len(frame_paths)}...")
        frame_b64 = image_to_base64(frame_path)

        previous_descriptions_limited = frame_descriptions[-MAX_PREVIOUS_DESCRIPTIONS:]

        human_content = [
            {"type": "text", "text": "Analizza il frame seguente. Tieni conto delle descrizioni dei frame precedenti fornite. Non generare analisi mediche. Cerca di mantenere coerenza con le descrizioni precedenti."},
        ]

        for idx, desc in enumerate(previous_descriptions_limited):
            human_content.append({"type": "text", "text": f"Descrizione frame precedente {idx+1}: {desc}"})

        human_content.append({"type": "image_url", "image_url": {"url": frame_b64, "detail": "auto"}})

        human_message = HumanMessage(content=human_content)

        print("Invio richiesta al modello per la descrizione del frame...")
        response = chat(messages + [human_message])
        ai_response = response.content

        print("Parsing della risposta del modello...")
        start_tag = "<attribute=frame_description|"
        end_tag = "| attribute=frame_description>"
        start_idx = ai_response.find(start_tag)
        end_idx = ai_response.find(end_tag)

        if start_idx == -1 or end_idx == -1:
            print("Errore: formato non corretto nella risposta del modello.")
            raise ValueError("La risposta del modello non contiene la descrizione formattata correttamente.")

        json_str = ai_response[start_idx+len(start_tag):end_idx].strip()
        try:
            desc_dict = json.loads(json_str)
            desc_frame = desc_dict.get("descrizione_frame", "")
            print(f"Descrizione frame {i+1} estratta con successo.")
        except:
            print("Errore nel parsing del JSON per la descrizione del frame.")
            raise ValueError("Errore nel parsing del JSON per la descrizione del frame.")

        messages.append(human_message)
        messages.append(AIMessage(content=ai_response))
        frame_descriptions.append(desc_frame)

    print("\nTutti i frame sono stati analizzati. Generazione della descrizione finale del video...")
    final_human_content = [
        {"type": "text", "text": "Genera la descrizione finale del video basandoti sulle descrizioni dei frame precedenti. Non analisi mediche, ma solo qualitative ed estetiche. Fornisci la descrizione finale racchiusa nei tag richiesti."},
    ]

    for idx, d in enumerate(frame_descriptions):
        final_human_content.append({"type": "text", "text": f"Descrizione frame {idx+1}: {d}"})

    final_human_message = HumanMessage(content=final_human_content)

    print("Invio richiesta al modello per la descrizione finale...")
    final_response = chat(messages + [final_human_message])
    final_text = final_response.content
    print("Parsing descrizione finale...")

    final_start_tag = "<attribute=final_description|"
    final_end_tag = "| attribute=final_description>"
    fs_idx = final_text.find(final_start_tag)
    fe_idx = final_text.find(final_end_tag)
    if fs_idx == -1 or fe_idx == -1:
        print("Errore: formato non corretto nella descrizione finale del modello.")
        raise ValueError("La risposta del modello non contiene la descrizione finale formattata correttamente.")
    final_json_str = final_text[fs_idx+len(final_start_tag):fe_idx].strip()

    try:
        final_desc_dict = json.loads(final_json_str)
        final_description = final_desc_dict.get("descrizione_finale", "")
        print("Descrizione finale estratta con successo.")
    except:
        print("Errore nel parsing del JSON per la descrizione finale.")
        raise ValueError("Errore nel parsing del JSON per la descrizione finale.")

    print("Processo completato con successo.")
    return {
        "frame_descriptions": frame_descriptions,
        "final_description": final_description
    }

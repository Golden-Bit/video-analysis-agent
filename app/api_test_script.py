import base64
import requests
import json

# Indirizzo dell'endpoint FastAPI, se l'app è in esecuzione in locale sulla porta 8000
URL = "http://localhost:8100/analyze_video"

# Carica un video di test dal filesystem e convertilo in base64
# Sostituisci "test_video.mp4" con il percorso del tuo video di prova
with open("test_video_2.mp4", "rb") as video_file:
    video_data = video_file.read()
    video_base64 = base64.b64encode(video_data).decode("utf-8")

# Prepara il payload della richiesta
payload = {
    "video_base64": video_base64,
    # È possibile specificare il numero di frame da estrarre o il frame rate
    # Se specificati entrambi, ha priorità num_frames
    "num_frames": 5,
    # "frame_rate": 1,  # In alternativa, specifica il frame_rate
    "width": 512,
    "height": 512
}

# Invia la richiesta POST
response = requests.post(URL, json=payload)

# Stampa la risposta
if response.status_code == 200:
    print("Risposta dal server:")
    print(json.dumps(response.json(), indent=2, ensure_ascii=False))
else:
    print(f"Errore {response.status_code}: {response.text}")

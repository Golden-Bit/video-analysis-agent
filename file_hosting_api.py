from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse
from pathlib import Path

app = FastAPI()

# Configurazione CORS
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],  # Puoi specificare i domini consentiti
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Percorso della cartella contenente i modelli 3D
MODELS_FOLDER = Path("./models")

@app.get("/")
def root():
    return {"message": "Backend per modelli 3D con FastAPI"}

@app.get("/models/{model_name}")
def get_model(model_name: str):
    model_path = MODELS_FOLDER / model_name
    if not model_path.exists():
        raise HTTPException(status_code=404, detail="Modello non trovato")
    return FileResponse(model_path)

# Avvia il server
if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8000)

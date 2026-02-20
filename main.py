import os
import requests
from fastapi import FastAPI
from dotenv import load_dotenv
from fastapi.responses import StreamingResponse
from fastapi.middleware.cors import CORSMiddleware

# Carrega variáveis de ambiente
load_dotenv()

# Cria o app
app = FastAPI()

# Libera acesso (CORS)
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Pega a chave da ElevenLabs
ELEVENLABS_API_KEY = os.getenv("ELEVENLABS_API_KEY")

# Rota inicial (teste)
@app.get("/")
def root():
    return {"status": "backend com voz funcionando"}

# Rota de fala
@app.get("/falar")
def falar(texto: str):
    url = "https://api.elevenlabs.io/v1/text-to-speech/EXAVITQu4vr4xnSDxMaL"

    headers = {
        "xi-api-key": ELEVENLABS_API_KEY,
        "Content-Type": "application/json"
    }

    data = {
        "text": texto,
        "voice_settings": {
            "stability": 0.5,
            "similarity_boost": 0.5
        }
    }

    response = requests.post(url, json=data, headers=headers)

    # Se der erro na API
    if response.status_code != 200:
        return {"erro": response.text}

    return StreamingResponse(
        iter([response.content]),
        media_type="audio/mpeg"
    )

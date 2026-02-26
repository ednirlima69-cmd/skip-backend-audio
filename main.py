from fastapi import FastAPI, HTTPException, Header
from fastapi.responses import StreamingResponse
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
from typing import Optional
import requests
import os
import io

app = FastAPI()

# =========================
# ✅ CORS
# =========================

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# =========================
# ✅ HEALTHCHECK
# =========================

@app.get("/")
def root():
    return {"status": "API rodando 🚀"}

# =========================
# 🔐 CONFIG
# =========================

ELEVEN_API_KEY = os.getenv("ELEVEN_API_KEY")

if not ELEVEN_API_KEY:
    raise Exception("ELEVEN_API_KEY não configurada")

# ⚠️ COLOQUE AQUI OS IDs REAIS DA SUA CONTA
VOICES = {
    "promocional": "Qrdut83w0Cr152Yb4Xn3",
    "institucional": "ZqE9vIHPcrC35dZv0Svu",
    "calmo": "ORgG8rwdAiMYRug8RJwR",
    "entusiasta": "MZxV5lN3cv7hi1376O0m"
}

# =========================
# 🎵 MODELO
# =========================

class AudioRequest(BaseModel):
    texto: str
    tom: Optional[str] = "neutro"

# =========================
# 🔊 FUNÇÃO REAL ELEVENLABS
# =========================

def gerar_audio_real(texto: str, tom: str):

    voice_id = VOICES.get(tom, VOICES["neutro"])

    url = f"https://api.elevenlabs.io/v1/text-to-speech/{voice_id}"

    headers = {
        "xi-api-key": ELEVEN_API_KEY,
        "Content-Type": "application/json"
    }

    data = {
        "text": texto,
        "model_id": "eleven_monolingual_v1"
    }

    response = requests.post(url, json=data, headers=headers)

    if response.status_code != 200:
        raise HTTPException(status_code=500, detail=response.text)

    return io.BytesIO(response.content)

# =========================
# 🔎 PREVIEW (NÃO CONSOME)
# =========================

@app.post("/audio/preview")
def preview_audio(request: AudioRequest, authorization: str = Header(None)):

    if not authorization:
        raise HTTPException(status_code=401, detail="Token não enviado")

    audio_stream = gerar_audio_real(request.texto, request.tom)

    return StreamingResponse(
        audio_stream,
        media_type="audio/mpeg"
    )

# =========================
# 🎙️ GENERATE (CONSUME)
# =========================

@app.post("/audio/generate")
def generate_audio(request: AudioRequest, authorization: str = Header(None)):

    if not authorization:
        raise HTTPException(status_code=401, detail="Token não enviado")

    audio_stream = gerar_audio_real(request.texto, request.tom)

    return StreamingResponse(
        audio_stream,
        media_type="audio/mpeg"
    )

# =========================
# 🎤 LISTAR VOZES DA SUA CONTA
# =========================

@app.get("/voices")
def listar_vozes():

    url = "https://api.elevenlabs.io/v1/voices"

    headers = {
        "xi-api-key": ELEVEN_API_KEY
    }

    response = requests.get(url, headers=headers)

    if response.status_code != 200:
        raise HTTPException(status_code=500, detail=response.text)

    return response.json()


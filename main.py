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
VOICE_ID = "EXAVITQu4vr4xnSDxMaL"  # voz padrão

# =========================
# 🎵 MODELO
# =========================

class AudioRequest(BaseModel):
    texto: str
    tom: Optional[str] = "neutro"

# =========================
# 🔊 FUNÇÃO REAL ELEVENLABS
# =========================

def gerar_audio_real(texto: str):
    url = f"https://api.elevenlabs.io/v1/text-to-speech/{VOICE_ID}"

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
        raise HTTPException(status_code=500, detail="Erro ao gerar áudio")

    return io.BytesIO(response.content)

# =========================
# 🔎 PREVIEW (NÃO CONSOME)
# =========================

@app.post("/audio/preview")
def preview_audio(request: AudioRequest, authorization: str = Header(None)):

    if not authorization:
        raise HTTPException(status_code=401, detail="Token não enviado")

    audio_stream = gerar_audio_real(request.texto)

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

    audio_stream = gerar_audio_real(request.texto)

    return StreamingResponse(
        audio_stream,
        media_type="audio/mpeg"
    )

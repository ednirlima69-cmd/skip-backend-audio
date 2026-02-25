from fastapi import FastAPI, HTTPException
from fastapi.responses import Response
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
import requests
import os
import re

app = FastAPI()

# ==============================
# 🔐 CORS (LIBERA FRONTEND)
# ==============================

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],  # depois podemos restringir só ao domínio do SKIP
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# ==============================
# 🔑 CHAVE ELEVENLABS
# ==============================

ELEVENLABS_API_KEY = os.getenv("ELEVENLABS_API_KEY")

if not ELEVENLABS_API_KEY:
    raise RuntimeError("ELEVENLABS_API_KEY não configurada no Railway")

# ==============================
# 🎙️ VOZES CONFIGURADAS
# ==============================

VOICES = {
    "promocional": "Qrdut83w0Cr152Yb4Xn3",
    "institucional": "ZqE9vIHPcrC35dZv0Svu",
    "calmo": "ORgG8rwdAiMYRug8RJwR",
    "entusiasta": "MZxV5lN3cv7hi1376O0m"
}

# ==============================
# 📦 MODELO DE REQUISIÇÃO
# ==============================

class TextoRequest(BaseModel):
    texto: str
    tom: str = "promocional"

# ==============================
# 💰 FORMATAR VALORES
# ==============================

def formatar_valores(texto):
    def substituir(match):
        valor = match.group(1)
        reais, centavos = valor.split(",")
        return f"{reais} reais e {centavos} centavos"
    return re.sub(r"R\$\s?(\d+,\d{2})", substituir, texto)

# ==============================
# 🏠 ROTA TESTE
# ==============================

@app.get("/")
def root():
    return {"status": "API ElevenLabs rodando 🚀"}

# ==============================
# 🎧 GERAR ÁUDIO
# ==============================

@app.post("/generate")
def gerar_audio(request: TextoRequest):

    tom_normalizado = request.tom.lower().strip()

    if tom_normalizado not in VOICES:
        raise HTTPException(status_code=400, detail="Tom inválido")

    texto_formatado = formatar_valores(request.texto)

    voice_id = VOICES[tom_normalizado]

    url = f"https://api.elevenlabs.io/v1/text-to-speech/{voice_id}"

    headers = {
        "xi-api-key": ELEVENLABS_API_KEY,
        "Content-Type": "application/json"
    }

    data = {
        "text": texto_formatado,
        "model_id": "eleven_multilingual_v2"
    }

    response = requests.post(url, json=data, headers=headers)

    if response.status_code != 200:
        raise HTTPException(
            status_code=500,
            detail=f"Erro ElevenLabs: {response.text}"
        )

    return Response(
        content=response.content,
        media_type="audio/mpeg",
        headers={
            "Content-Disposition": "inline; filename=audio.mp3"
        }
    )

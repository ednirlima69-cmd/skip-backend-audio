from fastapi import FastAPI, HTTPException
from fastapi.responses import Response
from pydantic import BaseModel
import requests
import os
import re

app = FastAPI()

ELEVENLABS_API_KEY = os.getenv("ELEVENLABS_API_KEY")

# 🔥 Suas vozes configuradas
VOICES = {
    "promocional": "Qrdut83w0Cr152Yb4Xn3",
    "institucional": "ZqE9vIHPcrC35dZv0Svu",
    "calmo": "ORgG8rwdAiMYRug8RJwR",
    "entusiasta": "MZxV5lN3cv7hi1376O0m"
}

class TextoRequest(BaseModel):
    texto: str
    tom: str = "promocional"


def formatar_valores(texto):
    def substituir(match):
        valor = match.group(1)
        reais, centavos = valor.split(",")
        return f"{reais} reais e {centavos} centavos"
    return re.sub(r"R\$\s?(\d+,\d{2})", substituir, texto)


@app.get("/")
def root():
    return {"status": "API ElevenLabs rodando 🚀"}


@app.post("/generate")
def gerar_audio(request: TextoRequest):

    if request.tom not in VOICES:
        raise HTTPException(status_code=400, detail="Tom inválido")

    texto_formatado = formatar_valores(request.texto)

    voice_id = VOICES[request.tom]

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
        raise HTTPException(status_code=500, detail="Erro ao gerar áudio")

    return Response(
        content=response.content,
        media_type="audio/mpeg",
        headers={
            "Content-Disposition": "inline; filename=audio.mp3"
        }
    )

from fastapi import FastAPI
from pydantic import BaseModel
from fastapi.responses import JSONResponse
from fastapi.middleware.cors import CORSMiddleware
import requests
import base64
import os
import re
from typing import Optional
from num2words import num2words

app = FastAPI()

# ✅ Rota raiz para healthcheck do Railway
@app.get("/")
def home():
    return {"status": "API ElevenLabs rodando 🚀"}

# ✅ CORS liberado
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

class AudioRequest(BaseModel):
    texto: str
    tom: Optional[str] = "promocional"

ELEVEN_API_KEY = os.getenv("ELEVEN_API_KEY")

# 🔥 Função para converter valores monetários automaticamente
def converter_valores_para_extenso(texto):
    padrao = r'R?\$?\s*(\d+),(\d{2})'

    def substituir(match):
        reais = int(match.group(1))
        centavos = int(match.group(2))

        texto_reais = num2words(reais, lang='pt_BR')
        texto_centavos = num2words(centavos, lang='pt_BR')

        if centavos == 0:
            return f"{texto_reais} reais"
        else:
            return f"{texto_reais} reais e {texto_centavos} centavos"

    return re.sub(padrao, substituir, texto)

@app.post("/generate")
async def generate_audio(request: AudioRequest):
    try:
        # 🔥 Converte valores automaticamente
        texto_tratado = converter_valores_para_extenso(request.texto)

        # 🔥 Mapeamento de tons para vozes
        VOICE_MAP = {
            "promocional": "Qrdut83w0Cr152Yb4Xn3",
            "institucional": "ZqE9vIHPcrC35dZv0Svu",
            "calmo": "ORgG8rwdAiMYRug8RJwR",
            "entusiasta": "MZxV5lN3cv7hi1376O0m"
        }

        voice_id = VOICE_MAP.get(request.tom, "COLOQUE_ID_1")

        url = f"https://api.elevenlabs.io/v1/text-to-speech/{voice_id}"

        headers = {
            "xi-api-key": ELEVEN_API_KEY,
            "Content-Type": "application/json"
        }

        data = {
            "text": texto_tratado,
            "model_id": "eleven_multilingual_v2"
        }

        response = requests.post(url, json=data, headers=headers)

        if response.status_code != 200:
            return JSONResponse(status_code=500, content={"error": response.text})

        audio_base64 = base64.b64encode(response.content).decode("utf-8")

        return {"audio": audio_base64}

    except Exception as e:
        return JSONResponse(status_code=500, content={"error": str(e)})

from fastapi import FastAPI
from pydantic import BaseModel
from fastapi.responses import JSONResponse
from fastapi.middleware.cors import CORSMiddleware
import requests
import base64
import os
from typing import Optional

app = FastAPI()

@app.get("/")
def home():
    return {"status": "API ElevenLabs rodando 🚀"}

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

@app.post("/generate")
async def generate_audio(request: AudioRequest):
    try:
        texto = request.texto

        # 🔥 Mapeamento de vozes
        VOICE_MAP = {
            "promocional": "COLOQUE_ID_1",
            "institucional": "COLOQUE_ID_2",
            "calmo": "COLOQUE_ID_3",
            "entusiasta": "COLOQUE_ID_4"
        }

        voice_id = VOICE_MAP.get(request.tom, "COLOQUE_ID_1")

        url = f"https://api.elevenlabs.io/v1/text-to-speech/{voice_id}"

        headers = {
            "xi-api-key": ELEVEN_API_KEY,
            "Content-Type": "application/json"
        }

        data = {
            "text": texto,
            "model_id": "eleven_multilingual_v2"
        }

        response = requests.post(url, json=data, headers=headers)

        if response.status_code != 200:
            return JSONResponse(status_code=500, content={"error": response.text})

        audio_base64 = base64.b64encode(response.content).decode("utf-8")

        return {"audio": audio_base64}

    except Exception as e:
        return JSONResponse(status_code=500, content={"error": str(e)})

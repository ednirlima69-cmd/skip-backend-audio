from fastapi import FastAPI, HTTPException, Header
from fastapi.responses import StreamingResponse
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
from typing import Optional
import requests
import os
import io
import re
from num2words import num2words

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

# =========================
# 🎙️ VOZES OFICIAIS E&K
# =========================

VOICES = {
    "ek_comercial_feminina": "ZqE9vIHPcrC35dZv0Svu",
    "ek_impacto_masculino": "Qrdut83w0Cr152Yb4Xn3",
    "ek_corporativo_masculino": "ORgG8rwdAiMYRug8RJwR",
    "ek_energia_feminina": "MZxV5lN3cv7hi1376O0m",
}

# =========================
# 🧠 SIMULAÇÃO BANCO (TEMPORÁRIO)
# =========================

users_db = {
    "mock_jwt_token_1772104488023": {
        "plan": "free",  # free | pro | pro_max
        "credits": 10
    }
}

# =========================
# 🎵 MODELO
# =========================

class AudioRequest(BaseModel):
    texto: str
    tom: Optional[str] = "ek_comercial_feminina"

# =========================
# 💰 NORMALIZAÇÃO DE MOEDA
# =========================

def normalizar_moeda(texto: str):

    padrao = r'R?\$?\s?(\d+),(\d{2})'

    def substituir(match):
        reais = int(match.group(1))
        centavos = int(match.group(2))

        texto_reais = num2words(reais, lang='pt_BR')

        if centavos == 0:
            return f"{texto_reais} reais"

        texto_centavos = num2words(centavos, lang='pt_BR')
        return f"{texto_reais} reais e {texto_centavos} centavos"

    texto = re.sub(padrao, substituir, texto)

    return texto

# =========================
# 🔊 ELEVENLABS
# =========================

def gerar_audio_real(texto: str, tom: str):

    texto = normalizar_moeda(texto)

    voice_id = VOICES.get(tom)

    if not voice_id:
        raise HTTPException(status_code=400, detail="Voz inválida")

    url = f"https://api.elevenlabs.io/v1/text-to-speech/{voice_id}"

    headers = {
        "xi-api-key": ELEVEN_API_KEY,
        "Content-Type": "application/json"
    }

    data = {
        "text": texto,
        "model_id": "eleven_multilingual_v2",
        "voice_settings": {
            "stability": 0.50,
            "similarity_boost": 0.75
        }
    }

    response = requests.post(url, json=data, headers=headers)

    if response.status_code != 200:
        raise HTTPException(status_code=500, detail=response.text)

    return io.BytesIO(response.content)

# =========================
# 🔒 VALIDAÇÃO DE PLANO
# =========================

def validar_plano(user, texto, tom):

    plano = user["plan"]

    # ---------------- FREE ----------------
    if plano == "free":
        if len(texto) > 300:
            raise HTTPException(status_code=403, detail="Limite de 300 caracteres no plano FREE")

        if tom != "ek_comercial_feminina":
            raise HTTPException(status_code=403, detail="Voz disponível apenas no plano PRO")

        if user["credits"] <= 0:
            raise HTTPException(status_code=403, detail="Créditos esgotados. Faça upgrade.")

    # ---------------- PRO ----------------
    elif plano == "pro":
        if len(texto) > 600:
            raise HTTPException(status_code=403, detail="Limite de 600 caracteres no plano PRO")

        vozes_permitidas = [
            "ek_comercial_feminina",
            "ek_impacto_masculino",
            "ek_corporativo_masculino"
        ]

        if tom not in vozes_permitidas:
            raise HTTPException(status_code=403, detail="Voz disponível apenas no PRO MAX")

        if user["credits"] <= 0:
            raise HTTPException(status_code=403, detail="Créditos mensais esgotados")

    # ---------------- PRO MAX ----------------
    elif plano == "pro_max":
        if len(texto) > 1000:
            raise HTTPException(status_code=403, detail="Limite de 1000 caracteres no PRO MAX")

    return True

# =========================
# 🎙️ GENERATE
# =========================

@app.post("/audio/generate")
def generate_audio(request: AudioRequest, authorization: str = Header(None)):

    if not authorization:
        raise HTTPException(status_code=401, detail="Token não enviado")

    token = authorization.replace("Bearer ", "")

    user = users_db.get(token)

    if not user:
        raise HTTPException(status_code=401, detail="Usuário inválido")

    validar_plano(user, request.texto, request.tom)

    # Debita crédito se não for PRO MAX
    if user["plan"] != "pro_max":
        user["credits"] -= 1

    texto_final = request.texto

    # Marca d'água no FREE
    if user["plan"] == "free":
        texto_final += " Áudio gerado com E e K Voice."

    audio_stream = gerar_audio_real(texto_final, request.tom)

    return StreamingResponse(
        audio_stream,
        media_type="audio/mpeg"
    )

# =========================
# 🎤 LISTAR VOZES
# =========================

@app.get("/voices")
def listar_vozes():
    return VOICES

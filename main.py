from fastapi import FastAPI, HTTPException, Header
from fastapi.responses import StreamingResponse
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
from typing import Optional
import requests
import os
import io
import re
import psycopg2
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
DATABASE_URL = os.getenv("DATABASE_URL")

if not ELEVEN_API_KEY:
    raise Exception("ELEVEN_API_KEY não configurada")

if not DATABASE_URL:
    raise Exception("DATABASE_URL não configurada")

def get_connection():
    return psycopg2.connect(DATABASE_URL)

# =========================
# 🗄️ CRIAR TABELA AUTOMÁTICA
# =========================

def create_tables():
    conn = get_connection()
    cur = conn.cursor()
    cur.execute("""
        CREATE TABLE IF NOT EXISTS users (
            id SERIAL PRIMARY KEY,
            token TEXT UNIQUE NOT NULL,
            plan TEXT DEFAULT 'free',
            credits INTEGER DEFAULT 10
        );
    """)
    conn.commit()
    cur.close()
    conn.close()

try:
    create_tables()
    print("Banco conectado com sucesso 🚀")
except Exception as e:
    print("Erro ao conectar no banco:", e)

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

    return re.sub(padrao, substituir, texto)

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

    if plano == "free":
        if len(texto) > 300:
            raise HTTPException(status_code=403, detail="Limite de 300 caracteres no plano FREE")

        if tom != "ek_comercial_feminina":
            raise HTTPException(status_code=403, detail="Voz disponível apenas no plano FREE")

        if user["credits"] <= 0:
            raise HTTPException(status_code=403, detail="Créditos esgotados. Faça upgrade.")

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

    elif plano == "pro_max":
        if len(texto) > 1000:
            raise HTTPException(status_code=403, detail="Limite de 1000 caracteres no PRO MAX")

    return True

# =========================
# 👤 ENDPOINT /me
# =========================

@app.get("/me")
def get_me(authorization: str = Header(None)):

    if not authorization:
        raise HTTPException(status_code=401, detail="Token não enviado")

    token = authorization.replace("Bearer ", "")

    conn = get_connection()
    cur = conn.cursor()

    cur.execute("SELECT plan, credits FROM users WHERE token = %s", (token,))
    user = cur.fetchone()

    # cria usuário automaticamente se não existir
    if not user:
        cur.execute(
            "INSERT INTO users (token) VALUES (%s) RETURNING plan, credits",
            (token,)
        )
        conn.commit()
        user = cur.fetchone()

    cur.close()
    conn.close()

    return {
        "plan": user[0],
        "credits": user[1] if user[0] != "pro_max" else "ilimitado"
    }

# =========================
# 🎙️ GENERATE
# =========================

@app.post("/audio/generate")
def generate_audio(request: AudioRequest, authorization: str = Header(None)):

    if not authorization:
        raise HTTPException(status_code=401, detail="Token não enviado")

    token = authorization.replace("Bearer ", "")

    conn = get_connection()
    cur = conn.cursor()

    cur.execute("SELECT plan, credits FROM users WHERE token = %s", (token,))
    result = cur.fetchone()

    if not result:
        raise HTTPException(status_code=401, detail="Usuário inválido")

    user = {
        "plan": result[0],
        "credits": result[1]
    }

    validar_plano(user, request.texto, request.tom)

    if user["plan"] != "pro_max":
        novo_credito = user["credits"] - 1

        cur.execute(
            "UPDATE users SET credits = %s WHERE token = %s",
            (novo_credito, token)
        )
        conn.commit()

    texto_final = request.texto

    if user["plan"] == "free":
        texto_final += " Áudio gerado com E e K Voice."

    cur.close()
    conn.close()

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


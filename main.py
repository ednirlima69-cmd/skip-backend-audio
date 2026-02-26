from fastapi import FastAPI, HTTPException, Header
from fastapi.responses import StreamingResponse
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
from typing import Optional
import io

app = FastAPI()

# =========================
# ✅ CORS (LIBERA SKIP)
# =========================

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],  # em produção depois restringimos
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# =========================
# ✅ HEALTHCHECK RAILWAY
# =========================

@app.get("/")
def root():
    return {"status": "API rodando 🚀"}


# =========================
# 🔐 USUÁRIOS MOCK
# =========================

users_db = {
    "EdnirLima": {
        "password": "Ednir@22031985@",
        "plan": "enterprise",
        "credits": 9999,
        "is_admin": True
    },
    "usuario_free": {
        "password": "123456",
        "plan": "free",
        "credits": 3,
        "is_admin": False
    }
}

# =========================
# 🎵 MODELO
# =========================

class AudioRequest(BaseModel):
    texto: str
    tom: Optional[str] = "neutro"


# =========================
# 🎙️ FAKE AUDIO
# =========================

def gerar_audio_fake(texto: str):
    fake_audio = f"Áudio gerado para: {texto}".encode()
    return io.BytesIO(fake_audio)


# =========================
# 🔎 PREVIEW (NÃO CONSOME)
# =========================

@app.post("/audio/preview")
def preview_audio(request: AudioRequest, authorization: str = Header(None)):

    if not authorization:
        raise HTTPException(status_code=401, detail="Token não enviado")

    audio_stream = gerar_audio_fake(request.texto)

    return StreamingResponse(
        audio_stream,
        media_type="audio/mpeg"
    )


# =========================
# 🎙️ GERAÇÃO FINAL
# =========================

@app.post("/audio/generate")
def generate_audio(request: AudioRequest, authorization: str = Header(None)):

    if not authorization:
        raise HTTPException(status_code=401, detail="Token não enviado")

    user = users_db["EdnirLima"]

    if user["plan"] == "free" and user["credits"] <= 0:
        raise HTTPException(status_code=403, detail="Sem créditos disponíveis")

    if user["plan"] != "enterprise":
        user["credits"] -= 1

    audio_stream = gerar_audio_fake(request.texto)

    return StreamingResponse(
        audio_stream,
        media_type="audio/mpeg"
    )


# =========================
# 📊 USER INFO
# =========================

@app.get("/me")
def get_user():
    user = users_db["EdnirLima"]
    return {
        "username": "EdnirLima",
        "plan": user["plan"],
        "credits": user["credits"]
    }

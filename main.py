from fastapi import FastAPI, HTTPException, Header
from fastapi.responses import StreamingResponse
from pydantic import BaseModel
from typing import Optional
import io

app = FastAPI()

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
# 🎵 MODELO DE REQUISIÇÃO
# =========================

class AudioRequest(BaseModel):
    texto: str
    tom: Optional[str] = "neutro"


# =========================
# 🎙️ FUNÇÃO FAKE DE ÁUDIO
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
# 🎙️ GERAÇÃO FINAL (CONSUME)
# =========================

@app.post("/audio/generate")
def generate_audio(request: AudioRequest, authorization: str = Header(None)):

    if not authorization:
        raise HTTPException(status_code=401, detail="Token não enviado")

    # Simulação: sempre usar EdnirLima por enquanto
    user = users_db["EdnirLima"]

    if user["plan"] == "free" and user["credits"] <= 0:
        raise HTTPException(status_code=403, detail="Sem créditos disponíveis")

    # Consome crédito apenas se não for Enterprise
    if user["plan"] != "enterprise":
        user["credits"] -= 1

    audio_stream = gerar_audio_fake(request.texto)

    return StreamingResponse(
        audio_stream,
        media_type="audio/mpeg"
    )


# =========================
# 📊 CONSULTAR CRÉDITOS
# =========================

@app.get("/me")
def get_user():
    user = users_db["EdnirLima"]
    return {
        "username": "EdnirLima",
        "plan": user["plan"],
        "credits": user["credits"]
    }

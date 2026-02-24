from fastapi import FastAPI
from pydantic import BaseModel
from fastapi.responses import JSONResponse
from fastapi.middleware.cors import CORSMiddleware
import base64
from gtts import gTTS
import io

app = FastAPI()

# ✅ ATIVAR CORS
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],  # depois podemos restringir
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

class AudioRequest(BaseModel):
    texto: str

@app.get("/")
def root():
    return {"status": "API rodando"}

@app.post("/generate")
async def generate_audio(request: AudioRequest):
    try:
        tts = gTTS(text=request.texto, lang="pt-br")
        audio_buffer = io.BytesIO()
        tts.write_to_fp(audio_buffer)
        audio_buffer.seek(0)

        audio_base64 = base64.b64encode(audio_buffer.read()).decode("utf-8")

        return {"audio": audio_base64}

    except Exception as e:
        return JSONResponse(status_code=500, content={"error": str(e)})

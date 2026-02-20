@app.get("/falar")
def falar(texto: str):
    url = "https://api.elevenlabs.io/v1/text-to-speech/EXAVITQu4vr4xnSDxMaL"

    headers = {
        "xi-api-key": ELEVENLABS_API_KEY,
        "Content-Type": "application/json"
    }

    data = {
        "text": texto,
        "voice_settings": {
            "stability": 0.5,
            "similarity_boost": 0.5
        }
    }

    response = requests.post(url, json=data, headers=headers)

    # 🔥 TRATAMENTO DE ERRO
    if response.status_code != 200:
        return {
            "erro": "Falha na API ElevenLabs",
            "status_code": response.status_code,
            "resposta": response.text
        }

    return StreamingResponse(
        iter([response.content]),
        media_type="audio/mpeg"
    )

from fastapi import FastAPI, HTTPException, Depends
from fastapi.middleware.cors import CORSMiddleware
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials
from fastapi.responses import Response
from pydantic import BaseModel
from typing import Optional
import requests
import os
import psycopg2
import bcrypt
from jose import JWTError, jwt
from datetime import datetime, timedelta

app = FastAPI()

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

ELEVEN_API_KEY = os.getenv("ELEVEN_API_KEY")
DATABASE_URL = os.getenv("DATABASE_URL")
SECRET_KEY = os.getenv("SECRET_KEY", "supersecretkey")

ALGORITHM = "HS256"
ACCESS_TOKEN_EXPIRE_DAYS = 30

security = HTTPBearer()

# =========================
# VOZES
# =========================
VOICES = {
    "promocional": "ZqE9vIHPcrC35dZv0Svu",
    "institucional": "Qrdut83w0Cr152Yb4Xn3",
    "calmo": "ORgG8rwdAiMYRug8RJwR",
    "entusiasta": "MZxV5lN3cv7hi1376O0m",
    "neutro": "ZqE9vIHPcrC35dZv0Svu"
}

def get_connection():
    return psycopg2.connect(DATABASE_URL)

def create_tables():
    conn = get_connection()
    cur = conn.cursor()
    cur.execute("""
    CREATE TABLE IF NOT EXISTS users (
        id SERIAL PRIMARY KEY,
        email TEXT UNIQUE NOT NULL,
        password_hash TEXT NOT NULL,
        plan TEXT DEFAULT 'free',
        credits INTEGER DEFAULT 10,
        role TEXT DEFAULT 'user',
        created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
    );
    """)
    conn.commit()
    cur.close()
    conn.close()

@app.on_event("startup")
def startup():
    if DATABASE_URL:
        create_tables()

class UserCreate(BaseModel):
    email: str
    password: str

class LoginRequest(BaseModel):
    email: str
    password: str

class AudioRequest(BaseModel):
    texto: str
    tom: Optional[str] = "promocional"

def create_access_token(data: dict):
    to_encode = data.copy()
    expire = datetime.utcnow() + timedelta(days=ACCESS_TOKEN_EXPIRE_DAYS)
    to_encode.update({"exp": expire})
    return jwt.encode(to_encode, SECRET_KEY, algorithm=ALGORITHM)

def get_current_user(credentials: HTTPAuthorizationCredentials = Depends(security)):
    token = credentials.credentials
    try:
        payload = jwt.decode(token, SECRET_KEY, algorithms=[ALGORITHM])
        user_id = payload.get("user_id")
    except JWTError:
        raise HTTPException(status_code=401, detail="Token inválido")

    conn = get_connection()
    cur = conn.cursor()
    cur.execute(
        "SELECT id,email,plan,credits,role FROM users WHERE id=%s",
        (user_id,)
    )
    user = cur.fetchone()
    cur.close()
    conn.close()

    if not user:
        raise HTTPException(status_code=401)

    return {
        "id": user[0],
        "email": user[1],
        "plan": user[2],
        "credits": user[3],
        "role": user[4]
    }

@app.get("/")
def root():
    return {"status": "AI E&K Generator PRO ONLINE"}

@app.get("/health")
def health():
    return {"status": "healthy"}

@app.get("/me")
def me(current_user: dict = Depends(get_current_user)):
    return current_user

@app.post("/register")
def register(user: UserCreate):
    hashed = bcrypt.hashpw(user.password.encode(), bcrypt.gensalt()).decode()
    conn = get_connection()
    cur = conn.cursor()
    try:
        cur.execute("""
        INSERT INTO users (email,password_hash,plan,credits,role)
        VALUES (%s,%s,'free',10,'user')
        """, (user.email, hashed))
        conn.commit()
    except Exception as e:
        raise HTTPException(status_code=400, detail=str(e))
    finally:
        cur.close()
        conn.close()
    return {"message": "Usuário criado"}

@app.post("/login")
def login(data: LoginRequest):
    conn = get_connection()
    cur = conn.cursor()
    cur.execute(
        "SELECT id,password_hash,role FROM users WHERE email=%s",
        (data.email,)
    )
    user = cur.fetchone()
    cur.close()
    conn.close()

    if not user:
        raise HTTPException(status_code=400, detail="Usuário não encontrado")

    user_id, password_hash, role = user

    if not bcrypt.checkpw(data.password.encode(), password_hash.encode()):
        raise HTTPException(status_code=400, detail="Senha inválida")

    token = create_access_token({"user_id": user_id, "role": role})

    return {
        "access_token": token,
        "token_type": "bearer"
    }

@app.get("/voices")
def voices():
    return [
        {"id": "promocional", "name": "Promocional"},
        {"id": "institucional", "name": "Institucional"},
        {"id": "calmo", "name": "Calmo"},
        {"id": "entusiasta", "name": "Entusiasta"},
        {"id": "neutro", "name": "Neutro"}
    ]

@app.get("/audio/test")
def test_audio():
    voice_id = VOICES["promocional"]
    url = f"https://api.elevenlabs.io/v1/text-to-speech/{voice_id}"
    headers = {
        "xi-api-key": ELEVEN_API_KEY,
        "Content-Type": "application/json",
        "Accept": "audio/mpeg"
    }
    payload = {
        "text": "Teste direto de voz funcionando",
        "model_id": "eleven_turbo_v2"
    }
    response = requests.post(url, json=payload, headers=headers)
    if response.status_code != 200:
        raise HTTPException(status_code=500, detail=response.text)
    return Response(content=response.content, media_type="audio/mpeg")

@app.post("/audio/generate")
def generate_audio(data: AudioRequest, current_user: dict = Depends(get_current_user)):
    voice_id = VOICES.get(data.tom, VOICES["promocional"])
    url = f"https://api.elevenlabs.io/v1/text-to-speech/{voice_id}"
    headers = {
        "xi-api-key": ELEVEN_API_KEY,
        "Content-Type": "application/json",
        "Accept": "audio/mpeg"
    }
    payload = {
        "text": data.texto,
        "model_id": "eleven_turbo_v2"
    }
    response = requests.post(url, json=payload, headers=headers)
    if response.status_code != 200:
        raise HTTPException(status_code=500, detail=response.text)
    return Response(content=response.content, media_type="audio/mpeg")

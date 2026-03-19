from fastapi import FastAPI, HTTPException, Depends
from fastapi.middleware.cors import CORSMiddleware
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials
from pydantic import BaseModel
from typing import Optional
import requests
import os
import psycopg2
import bcrypt
import re
import base64
from num2words import num2words
from jose import JWTError, jwt
from datetime import datetime, timedelta
import uuid

app = FastAPI()

# =========================
# CORS
# =========================
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# =========================
# CONFIG
# =========================
ELEVEN_API_KEY = os.getenv("ELEVEN_API_KEY")
DATABASE_URL = os.getenv("DATABASE_URL")
SECRET_KEY = os.getenv("SECRET_KEY", "supersecretkey")

ALGORITHM = "HS256"
ACCESS_TOKEN_EXPIRE_DAYS = 30

security = HTTPBearer()

# =========================
# VOZES (SUAS ORIGINAIS)
# =========================
VOICES = {
    "promocional": "ZqE9vIHPcrC35dZv0Svu",
    "institucional": "Qrdut83w0Cr152Yb4Xn3",
    "calmo": "ORgG8rwdAiMYRug8RJwR",
    "entusiasta": "MZxV5lN3cv7hi1376O0m",
    "neutro": "ZqE9vIHPcrC35dZv0Svu"
}

# =========================
# BANCO
# =========================
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

# =========================
# MODELOS
# =========================
class UserCreate(BaseModel):
    email: str
    password: str

class LoginRequest(BaseModel):
    email: str
    password: str

class AudioRequest(BaseModel):
    texto: str
    tom: Optional[str] = "promocional"

# =========================
# JWT
# =========================
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

# =========================
# ROTAS BASICAS
# =========================
@app.get("/")
def root():
    return {"status": "AI E&K Generator PRO ONLINE"}

@app.get("/health")
def health():
    return {"status": "healthy"}

# =========================
# REGISTER
# =========================
@app.post("/register")
def register(user: UserCreate):

    hashed = bcrypt.hashpw(user.password.encode(), bcrypt.gensalt()).decode()

    conn = get_connection()
    cur = conn.cursor()

    cur.execute("SELECT COUNT(*) FROM users")
    total_users = cur.fetchone()[0]

    role = "admin" if total_users == 0 else "user"

    try:
        cur.execute("""
        INSERT INTO users (email,password_hash,plan,credits,role)
        VALUES (%s,%s,'free',10,%s)
        """,(user.email,hashed,role))

        conn.commit()

    except:
        raise HTTPException(status_code=400,detail="Email já cadastrado")

    finally:
        cur.close()
        conn.close()

    return {"message":"Usuário criado","role":role}

# =========================
# LOGIN
# =========================
@app.post("/login")
def login(data: LoginRequest):

    conn=get_connection()
    cur=conn.cursor()

    cur.execute(
        "SELECT id,password_hash,role FROM users WHERE email=%s",
        (data.email,)
    )

    db_user=cur.fetchone()

    cur.close()
    conn.close()

    if not db_user:
        raise HTTPException(status_code=400, detail="Usuário não encontrado")

    user_id,password_hash,role=db_user

    if not bcrypt.checkpw(data.password.encode(),password_hash.encode()):
        raise HTTPException(status_code=400, detail="Senha inválida")

    token=create_access_token({"user_id":user_id,"role":role})

    return {
        "access_token":token,
        "token_type":"bearer"
    }

# =========================
# AUDIO (MELHORADO)
# =========================
@app.post("/audio/generate")
def generate_audio(data:AudioRequest,current_user:dict=Depends(get_current_user)):

    if not ELEVEN_API_KEY:
        raise HTTPException(status_code=500,detail="API ElevenLabs não configurada")

    if current_user["role"]!="admin" and current_user["credits"]<=0:
        raise HTTPException(status_code=403, detail="Sem créditos")

    voice_id = VOICES.get(data.tom, VOICES["promocional"])

    # 🔢 Converter números
    texto = re.sub(
        r'\d+',
        lambda x: num2words(int(x.group()), lang='pt_BR'),
        data.texto
    )

    try:
        url = f"https://api.elevenlabs.io/v1/text-to-speech/{voice_id}"

        headers = {
            "xi-api-key": ELEVEN_API_KEY,
            "Content-Type": "application/json"
        }

        payload = {
            "text": texto,
            "model_id": "eleven_multilingual_v2"
        }

        response = requests.post(url, json=payload, headers=headers)

        if response.status_code != 200:
            raise HTTPException(status_code=500, detail=f"Erro ElevenLabs: {response.text}")

        audio_base64 = base64.b64encode(response.content).decode()

        audio_id = str(uuid.uuid4())

        # 🔻 descontar crédito
        if current_user["role"] != "admin":
            conn = get_connection()
            cur = conn.cursor()

            cur.execute(
                "UPDATE users SET credits=GREATEST(credits-1,0) WHERE id=%s",
                (current_user["id"],)
            )

            conn.commit()
            cur.close()
            conn.close()

        return {
            "status": "sucesso",
            "audio_id": audio_id,
            "voice": data.tom,
            "texto_processado": texto,
            "audio_base64": audio_base64
        }

    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

from fastapi import FastAPI, HTTPException, Depends
from fastapi.responses import StreamingResponse
from fastapi.middleware.cors import CORSMiddleware
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials
from pydantic import BaseModel
from typing import Optional
import requests
import os
import io
import re
import psycopg2
import bcrypt
import secrets
from num2words import num2words
from jose import JWTError, jwt
from datetime import datetime, timedelta

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

if not ELEVEN_API_KEY:
    raise Exception("ELEVEN_API_KEY não configurada")

if not DATABASE_URL:
    raise Exception("DATABASE_URL não configurada")

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

    cur.execute("""
        CREATE TABLE IF NOT EXISTS password_resets (
            id SERIAL PRIMARY KEY,
            email TEXT,
            token TEXT,
            expires_at TIMESTAMP
        );
    """)

    conn.commit()
    cur.close()
    conn.close()

@app.on_event("startup")
def startup_event():
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

class ForgotPassword(BaseModel):
    email: str

class ResetPassword(BaseModel):
    token: str
    new_password: str

# =========================
# JWT
# =========================

def create_access_token(data: dict):
    to_encode = data.copy()
    expire = datetime.utcnow() + timedelta(days=ACCESS_TOKEN_EXPIRE_DAYS)
    to_encode.update({"exp": expire})
    return jwt.encode(to_encode, SECRET_KEY, algorithm=ALGORITHM)

# =========================
# TOKEN AUTH
# =========================

security = HTTPBearer()

def get_current_user(credentials: HTTPAuthorizationCredentials = Depends(security)):
    token = credentials.credentials

    try:
        payload = jwt.decode(token, SECRET_KEY, algorithms=[ALGORITHM])
        user_id = payload.get("user_id")
        role = payload.get("role")
    except JWTError:
        raise HTTPException(status_code=401, detail="Token inválido")

    conn = get_connection()
    cur = conn.cursor()

    cur.execute(
        "SELECT id, email, plan, credits, role FROM users WHERE id = %s",
        (user_id,)
    )

    user = cur.fetchone()

    cur.close()
    conn.close()

    if not user:
        raise HTTPException(status_code=401, detail="Usuário não encontrado")

    return {
        "id": user[0],
        "email": user[1],
        "plan": user[2],
        "credits": user[3],
        "role": user[4]
    }

def admin_required(current_user: dict = Depends(get_current_user)):
    if current_user["role"] != "admin":
        raise HTTPException(status_code=403, detail="Apenas admin pode acessar")
    return current_user

# =========================
# ROTAS BÁSICAS
# =========================

@app.get("/")
def root():
    return {"status": "AI E&K Generator PRO ONLINE 🚀"}

@app.get("/health")
def health():
    return {"status": "healthy"}

# =========================
# REGISTER
# =========================

@app.post("/register")
def register(user: UserCreate):

    hashed = bcrypt.hashpw(user.password.encode(), bcrypt.gensalt()).decode()

    try:
        conn = get_connection()
        cur = conn.cursor()

        cur.execute(
            "INSERT INTO users (email, password_hash) VALUES (%s,%s)",
            (user.email, hashed)
        )

        conn.commit()
        cur.close()
        conn.close()

        return {"message": "Usuário criado"}

    except:
        raise HTTPException(status_code=400, detail="Email já cadastrado")

# =========================
# LOGIN
# =========================

@app.post("/login")
def login(data: LoginRequest):

    conn = get_connection()
    cur = conn.cursor()

    cur.execute(
        "SELECT id,password_hash,role FROM users WHERE email=%s",
        (data.email,)
    )

    db_user = cur.fetchone()

    cur.close()
    conn.close()

    if not db_user:
        raise HTTPException(status_code=400, detail="Usuário não encontrado")

    user_id,password_hash,role = db_user

    if not bcrypt.checkpw(data.password.encode(), password_hash.encode()):
        raise HTTPException(status_code=400, detail="Senha incorreta")

    token = create_access_token({
        "user_id": user_id,
        "role": role
    })

    return {"access_token": token,"token_type":"bearer"}

# =========================
# FORGOT PASSWORD
# =========================

@app.post("/forgot-password")
def forgot_password(data: ForgotPassword):

    token = secrets.token_urlsafe(32)

    expire = datetime.utcnow() + timedelta(hours=1)

    conn = get_connection()
    cur = conn.cursor()

    cur.execute(
        "INSERT INTO password_resets (email,token,expires_at) VALUES (%s,%s,%s)",
        (data.email,token,expire)
    )

    conn.commit()

    cur.close()
    conn.close()

    return {
        "message":"Token gerado",
        "reset_token":token
    }

# =========================
# RESET PASSWORD
# =========================

@app.post("/reset-password")
def reset_password(data: ResetPassword):

    conn = get_connection()
    cur = conn.cursor()

    cur.execute(
        "SELECT email,expires_at FROM password_resets WHERE token=%s",
        (data.token,)
    )

    record = cur.fetchone()

    if not record:
        raise HTTPException(status_code=400,detail="Token inválido")

    email,expires = record

    if datetime.utcnow() > expires:
        raise HTTPException(status_code=400,detail="Token expirado")

    hashed = bcrypt.hashpw(data.new_password.encode(), bcrypt.gensalt()).decode()

    cur.execute(
        "UPDATE users SET password_hash=%s WHERE email=%s",
        (hashed,email)
    )

    conn.commit()

    cur.execute(
        "DELETE FROM password_resets WHERE token=%s",
        (data.token,)
    )

    conn.commit()

    cur.close()
    conn.close()

    return {"message":"Senha redefinida com sucesso"}

# =========================
# GERAR AUDIO
# =========================

@app.post("/audio/generate")
def generate_audio(
    data: AudioRequest,
    current_user: dict = Depends(get_current_user)
):

    if current_user["role"] != "admin" and current_user["credits"] <= 0:
        raise HTTPException(status_code=403, detail="Sem créditos")

    voice_id = VOICES.get(data.tom)

    texto_processado = re.sub(
        r'\d+',
        lambda x: num2words(int(x.group()), lang='pt_BR'),
        data.texto
    )

    url = f"https://api.elevenlabs.io/v1/text-to-speech/{voice_id}"

    headers = {
        "xi-api-key": ELEVEN_API_KEY,
        "Content-Type":"application/json"
    }

    payload = {
        "text": texto_processado,
        "model_id":"eleven_multilingual_v2"
    }

    response = requests.post(url,json=payload,headers=headers)

    if response.status_code != 200:
        raise HTTPException(status_code=500,detail="Erro gerar audio")

    if current_user["role"] != "admin":

        conn = get_connection()
        cur = conn.cursor()

        cur.execute(
            "UPDATE users SET credits=credits-1 WHERE id=%s",
            (current_user["id"],)
        )

        conn.commit()

        cur.close()
        conn.close()

    return StreamingResponse(io.BytesIO(response.content),media_type="audio/mpeg")

# =========================
# ADMIN
# =========================

@app.get("/admin/dashboard")
def admin_dashboard(current_user: dict = Depends(admin_required)):
    return {
        "message":"Painel Admin",
        "usuario":current_user["email"],
        "plano":current_user["plan"],
        "credits":current_user["credits"]
    }

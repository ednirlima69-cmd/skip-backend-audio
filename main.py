from fastapi import FastAPI, HTTPException, Header, Depends
from fastapi.responses import StreamingResponse
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
from typing import Optional
import requests
import os
import io
import re
import psycopg2
import bcrypt
from num2words import num2words
from jose import JWTError, jwt
from datetime import datetime, timedelta

app = FastAPI()

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

def get_connection():
    return psycopg2.connect(DATABASE_URL)

# =========================
# BANCO
# =========================

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

create_tables()

# =========================
# MODELOS
# =========================

class UserCreate(BaseModel):
    email: str
    password: str

class UserLogin(BaseModel):
    email: str
    password: str

class AudioRequest(BaseModel):
    texto: str
    tom: Optional[str] = "ek_comercial_feminina"

# =========================
# JWT
# =========================

def create_access_token(data: dict):
    to_encode = data.copy()
    expire = datetime.utcnow() + timedelta(days=ACCESS_TOKEN_EXPIRE_DAYS)
    to_encode.update({"exp": expire})
    return jwt.encode(to_encode, SECRET_KEY, algorithm=ALGORITHM)

def get_current_user(authorization: str = Header(None)):
    if not authorization:
        raise HTTPException(status_code=401, detail="Token não enviado")

    token = authorization.replace("Bearer ", "")

    try:
        payload = jwt.decode(token, SECRET_KEY, algorithms=[ALGORITHM])
        user_id: int = payload.get("user_id")
    except JWTError:
        raise HTTPException(status_code=401, detail="Token inválido ou expirado")

    conn = get_connection()
    cur = conn.cursor()
    cur.execute("SELECT id, email, plan, credits, role FROM users WHERE id = %s", (user_id,))
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

# =========================
# REGISTER
# =========================

@app.post("/register")
def register(user: UserCreate):
    hashed = bcrypt.hashpw(user.password.encode(), bcrypt.gensalt())

    try:
        conn = get_connection()
        cur = conn.cursor()
        cur.execute(
            "INSERT INTO users (email, password_hash) VALUES (%s, %s)",
            (user.email, hashed.decode())
        )
        conn.commit()
        cur.close()
        conn.close()
        return {"message": "Usuário criado com sucesso"}
    except:
        raise HTTPException(status_code=400, detail="Email já cadastrado")

# =========================
# LOGIN
# =========================

@app.post("/login")
def login(user: UserLogin):

    conn = get_connection()
    cur = conn.cursor()
    cur.execute("SELECT id, password_hash, role FROM users WHERE email = %s", (user.email,))
    db_user = cur.fetchone()
    cur.close()
    conn.close()

    if not db_user:
        raise HTTPException(status_code=400, detail="Usuário não encontrado")

    user_id, password_hash, role = db_user

    if not bcrypt.checkpw(user.password.encode(), password_hash.encode()):
        raise HTTPException(status_code=400, detail="Senha incorreta")

    access_token = create_access_token({
        "user_id": user_id,
        "role": role
    })

    return {"access_token": access_token}

# =========================
# /ME
# =========================

@app.get("/me")
def me(current_user: dict = Depends(get_current_user)):
    return {
        "email": current_user["email"],
        "plan": current_user["plan"],
        "credits": current_user["credits"],
        "role": current_user["role"]
    }

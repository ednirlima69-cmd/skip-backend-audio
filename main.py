from fastapi import FastAPI, HTTPException, Depends, Request
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
import uuid
import cloudinary
import cloudinary.uploader

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
MP_ACCESS_TOKEN = os.getenv("MP_ACCESS_TOKEN")
MP_PUBLIC_KEY = os.getenv("MP_PUBLIC_KEY")

ALGORITHM = "HS256"
ACCESS_TOKEN_EXPIRE_DAYS = 30

security = HTTPBearer()

# =========================
# CLOUDINARY CONFIG
# =========================
cloudinary.config(
    cloud_name=os.getenv("CLOUDINARY_CLOUD_NAME"),
    api_key=os.getenv("CLOUDINARY_API_KEY"),
    api_secret=os.getenv("CLOUDINARY_API_SECRET")
)

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
# PLANOS
# =========================
PLANS = {
    "pro": {
        "name": "Plano Pro",
        "price": 29.90,
        "credits": 100,
        "type": "subscription"
    },
    "premium": {
        "name": "Plano Premium",
        "price": 99.90,
        "credits": 999999,
        "type": "subscription"
    },
    "avulso": {
        "name": "Pacote Avulso",
        "price": 19.90,
        "credits": 20,
        "type": "one_time"
    }
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

    cur.execute("""
    CREATE TABLE IF NOT EXISTS payments (
        id SERIAL PRIMARY KEY,
        user_id INTEGER REFERENCES users(id),
        mp_payment_id TEXT,
        plan TEXT,
        amount NUMERIC,
        status TEXT DEFAULT 'pending',
        created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
    );
    """)

    cur.execute("""
    CREATE TABLE IF NOT EXISTS audio_history (
        id SERIAL PRIMARY KEY,
        user_id INTEGER REFERENCES users(id),
        project_name TEXT,
        texto TEXT,
        tom TEXT,
        audio_url TEXT,
        cloudinary_public_id TEXT,
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
    project_name: Optional[str] = "Sem título"

class PaymentRequest(BaseModel):
    plan: str
    token: Optional[str] = None
    payment_method: str = "pix"
    installments: Optional[int] = 1
    issuer_id: Optional[str] = None

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

def deduct_credit(user_id: int):
    conn = get_connection()
    cur = conn.cursor()
    cur.execute(
        "UPDATE users SET credits = credits - 1 WHERE id = %s",
        (user_id,)
    )
    conn.commit()
    cur.close()
    conn.close()

def apply_plan(user_id: int, plan: str):
    plan_data = PLANS[plan]
    conn = get_connection()
    cur = conn.cursor()

    if plan_data["type"] == "one_time":
        cur.execute(
            "UPDATE users SET credits = credits + %s WHERE id = %s",
            (plan_data["credits"], user_id)
        )
    else:
        cur.execute(
            "UPDATE users SET plan = %s, credits = %s WHERE id = %s",
            (plan, plan_data["credits"], user_id)
        )

    conn.commit()
    cur.close()
    conn.close()

def save_audio_history(user_id: int, project_name: str, texto: str, tom: str, audio_url: str, cloudinary_public_id: str):
    conn = get_connection()
    cur = conn.cursor()
    cur.execute("""
        INSERT INTO audio_history (user_id, project_name, texto, tom, audio_url, cloudinary_public_id)
        VALUES (%s, %s, %s, %s, %s, %s)
    """, (user_id, project_name, texto, tom, audio_url, cloudinary_public_id))
    conn.commit()
    cur.close()
    conn.close()

@app.get("/")
def root():
    return {"status": "AI E&K Generator PRO ONLINE"}

@app.get("/health")
def health():
    return {"status": "healthy"}

@app.get("/me")
def me(current_user: dict = Depends(get_current_user)):
    return current_user

@app.get("/plans")
def get_plans():
    return [
        {"id": "avulso", "name": "Pacote Avulso", "price": 19.90, "credits": 20, "type": "one_time"},
        {"id": "pro", "name": "Plano Pro", "price": 29.90, "credits": 100, "type": "subscription"},
        {"id": "premium", "name": "Plano Premium", "price": 99.90, "credits": "ilimitado", "type": "subscription"}
    ]

@app.get("/mp/public-key")
def get_public_key():
    return {"public_key": MP_PUBLIC_KEY}

@app.get("/audio/history")
def get_audio_history(current_user: dict = Depends(get_current_user)):
    conn = get_connection()
    cur = conn.cursor()
    cur.execute("""
        SELECT id, project_name, texto, tom, audio_url, created_at
        FROM audio_history
        WHERE user_id = %s
        ORDER BY created_at DESC
        LIMIT 50
    """, (current_user["id"],))

    rows = cur.fetchall()
    cur.close()
    conn.close()

    return [
        {
            "id": row[0],
            "project_name": row[1],
            "texto": row[2],
            "tom": row[3],
            "audio_url": row[4],
            "created_at": row[5].strftime("%d/%m/%Y %H:%M")
        }
        for row in rows
    ]

@app.delete("/audio/history/{audio_id}")
def delete_audio(audio_id: int, current_user: dict = Depends(get_current_user)):
    conn = get_connection()
    cur = conn.cursor()

    cur.execute(
        "SELECT cloudinary_public_id, user_id FROM audio_history WHERE id = %s",
        (audio_id,)
    )
    row = cur.fetchone()

    if not row:
        raise HTTPException(status_code=404, detail="Áudio não encontrado")

    cloudinary_public_id, owner_id = row

    if owner_id != current_user["id"] and current_user["role"] != "admin":
        raise HTTPException(status_code=403, detail="Sem permissão")

    if cloudinary_public_id:
        try:
            cloudinary.uploader.destroy(
                cloudinary_public_id,
                resource_type="video"
            )
        except Exception:
            pass

    cur.execute("DELETE FROM audio_history WHERE id = %s", (audio_id,))
    conn.commit()
    cur.close()
    conn.close()

    return {"message": "Áudio excluído com sucesso"}

@app.post("/payment/create")
def create_payment(data: PaymentRequest, current_user: dict = Depends(get_current_user)):

    if data.plan not in PLANS:
        raise HTTPException(status_code=400, detail="Plano inválido")

    plan_data = PLANS[data.plan]
    idempotency_key = str(uuid.uuid4())

    headers = {
        "Authorization": f"Bearer {MP_ACCESS_TOKEN}",
        "Content-Type": "application/json",
        "X-Idempotency-Key": idempotency_key
    }

    payload = {
        "transaction_amount": float(plan_data["price"]),
        "description": plan_data["name"],
        "payment_method_id": data.payment_method,
        "payer": {
            "email": current_user["email"]
        },
        "metadata": {
            "user_id": str(current_user["id"]),
            "plan": data.plan
        }
    }

    if data.payment_method == "credit_card":
        if not data.token:
            raise HTTPException(status_code=400, detail="Token do cartão obrigatório")
        payload["token"] = data.token
        payload["installments"] = data.installments or 1
        if data.issuer_id:
            payload["issuer_id"] = data.issuer_id

    response = requests.post(
        "https://api.mercadopago.com/v1/payments",
        json=payload,
        headers=headers
    )

    result = response.json()

    if response.status_code not in [200, 201]:
        raise HTTPException(status_code=400, detail=result.get("message", "Erro ao criar pagamento"))

    conn = get_connection()
    cur = conn.cursor()
    cur.execute("""
        INSERT INTO payments (user_id, mp_payment_id, plan, amount, status)
        VALUES (%s, %s, %s, %s, %s)
    """, (
        current_user["id"],
        str(result["id"]),
        data.plan,
        plan_data["price"],
        result["status"]
    ))
    conn.commit()
    cur.close()
    conn.close()

    if result["status"] == "approved":
        apply_plan(current_user["id"], data.plan)

    response_data = {
        "payment_id": result["id"],
        "status": result["status"],
        "plan": data.plan
    }

    if data.payment_method == "pix":
        pix_data = result.get("point_of_interaction", {}).get("transaction_data", {})
        response_data["pix_qr_code"] = pix_data.get("qr_code")
        response_data["pix_qr_code_base64"] = pix_data.get("qr_code_base64")

    return response_data

@app.post("/webhook/mp")
async def webhook_mp(request: Request):
    body = await request.json()

    if body.get("type") != "payment":
        return {"status": "ignored"}

    payment_id = body.get("data", {}).get("id")
    if not payment_id:
        return {"status": "no payment id"}

    headers = {"Authorization": f"Bearer {MP_ACCESS_TOKEN}"}
    response = requests.get(
        f"https://api.mercadopago.com/v1/payments/{payment_id}",
        headers=headers
    )

    payment = response.json()

    if payment.get("status") != "approved":
        return {"status": "not approved"}

    metadata = payment.get("metadata", {})
    user_id = metadata.get("user_id")
    plan = metadata.get("plan")

    if not user_id or not plan:
        return {"status": "missing metadata"}

    conn = get_connection()
    cur = conn.cursor()
    cur.execute(
        "UPDATE payments SET status = 'approved' WHERE mp_payment_id = %s",
        (str(payment_id),)
    )
    conn.commit()
    cur.close()
    conn.close()

    apply_plan(int(user_id), plan)

    return {"status": "ok"}

@app.get("/payment/status/{payment_id}")
def payment_status(payment_id: str, current_user: dict = Depends(get_current_user)):
    headers = {"Authorization": f"Bearer {MP_ACCESS_TOKEN}"}
    response = requests.get(
        f"https://api.mercadopago.com/v1/payments/{payment_id}",
        headers=headers
    )
    result = response.json()
    return {
        "payment_id": payment_id,
        "status": result.get("status"),
        "status_detail": result.get("status_detail")
    }

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

    return {"access_token": token, "token_type": "bearer"}

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
        "model_id": "eleven_multilingual_v2",
        "language_code": "pt"
    }
    response = requests.post(url, json=payload, headers=headers)
    if response.status_code != 200:
        raise HTTPException(status_code=500, detail=response.text)
    return Response(content=response.content, media_type="audio/mpeg")

@app.post("/audio/generate")
def generate_audio(data: AudioRequest, current_user: dict = Depends(get_current_user)):

    if current_user["role"] != "admin":
        if current_user["credits"] <= 0:
            raise HTTPException(
                status_code=402,
                detail="Créditos esgotados. Faça upgrade do seu plano para continuar."
            )

    voice_id = VOICES.get(data.tom, VOICES["promocional"])
    url = f"https://api.elevenlabs.io/v1/text-to-speech/{voice_id}"
    headers = {
        "xi-api-key": ELEVEN_API_KEY,
        "Content-Type": "application/json",
        "Accept": "audio/mpeg"
    }
    payload = {
        "text": data.texto,
        "model_id": "eleven_multilingual_v2",
        "language_code": "pt"
    }

    response = requests.post(url, json=payload, headers=headers)

    if response.status_code != 200:
        raise HTTPException(status_code=500, detail=response.text)

    public_id = f"audio_{current_user['id']}_{uuid.uuid4().hex[:8]}"
    upload_result = cloudinary.uploader.upload(
        response.content,
        resource_type="video",
        public_id=public_id,
        folder="ek_generator",
        format="mp3"
    )
    audio_url = upload_result.get("secure_url")

    if current_user["role"] != "admin":
        deduct_credit(current_user["id"])

    save_audio_history(
        current_user["id"],
        data.project_name,
        data.texto,
        data.tom,
        audio_url,
        upload_result.get("public_id")
    )

    return {
        "audio_url": audio_url,
        "message": "Áudio gerado com sucesso"
    }

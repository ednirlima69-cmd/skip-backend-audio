from fastapi import FastAPI, HTTPException, Depends, Request, UploadFile, File, Form
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
import secrets
from pydub import AudioSegment
import io
import re

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
RESEND_API_KEY = os.getenv("RESEND_API_KEY")
ADMIN_EMAIL = os.getenv("ADMIN_EMAIL", "ednir-lima@hotmail.com")
FRONTEND_URL = os.getenv("FRONTEND_URL", "https://ai-ek-generator-pro-b35e6--preview.goskip.app")

ALGORITHM = "HS256"
ACCESS_TOKEN_EXPIRE_DAYS = 30

security = HTTPBearer()

cloudinary.config(
    cloud_name=os.getenv("CLOUDINARY_CLOUD_NAME"),
    api_key=os.getenv("CLOUDINARY_API_KEY"),
    api_secret=os.getenv("CLOUDINARY_API_SECRET")
)

VOICES = {
    "promocional": "ZqE9vIHPcrC35dZv0Svu",
    "institucional": "Qrdut83w0Cr152Yb4Xn3",
    "calmo": "ORgG8rwdAiMYRug8RJwR",
    "entusiasta": "MZxV5lN3cv7hi1376O0m",
    "neutro": "czvzJwIVS2asEKnthV40"
}

PLAN_RULES = {
    "free": {"voices": ["calmo", "neutro"], "max_chars": 300},
    "avulso": {"voices": ["calmo", "neutro"], "max_chars": 300},
    "pro": {"voices": ["calmo", "neutro", "institucional"], "max_chars": 600},
    "premium": {"voices": ["promocional", "institucional", "calmo", "entusiasta", "neutro"], "max_chars": 99999}
}

PLANS = {
    "pro": {"name": "Plano Pro", "price": 29.90, "credits": 100, "type": "subscription"},
    "premium": {"name": "Plano Premium", "price": 99.90, "credits": 999999, "type": "subscription"},
    "avulso": {"name": "Pacote Avulso", "price": 19.90, "credits": 20, "type": "one_time"}
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
        has_music BOOLEAN DEFAULT FALSE,
        created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
    );
    """)
    cur.execute("""
    CREATE TABLE IF NOT EXISTS support_tickets (
        id SERIAL PRIMARY KEY,
        user_id INTEGER REFERENCES users(id),
        nome TEXT,
        email TEXT,
        assunto TEXT,
        mensagem TEXT,
        status TEXT DEFAULT 'aberto',
        created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
    );
    """)
    cur.execute("""
    CREATE TABLE IF NOT EXISTS password_resets (
        id SERIAL PRIMARY KEY,
        user_id INTEGER REFERENCES users(id),
        token TEXT UNIQUE NOT NULL,
        expires_at TIMESTAMP NOT NULL,
        used BOOLEAN DEFAULT FALSE,
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
    tom: Optional[str] = "calmo"
    project_name: Optional[str] = "Sem titulo"


class PaymentRequest(BaseModel):
    plan: str
    token: Optional[str] = None
    payment_method: str = "pix"
    installments: Optional[int] = 1
    issuer_id: Optional[str] = None


class UpdateUserRequest(BaseModel):
    plan: Optional[str] = None
    credits: Optional[int] = None
    role: Optional[str] = None


class SupportRequest(BaseModel):
    nome: str
    email: str
    assunto: str
    mensagem: str


class ForgotPasswordRequest(BaseModel):
    email: str


class ResetPasswordRequest(BaseModel):
    token: str
    new_password: str


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
        raise HTTPException(status_code=401, detail="Token invalido")

    conn = get_connection()
    cur = conn.cursor()
    cur.execute("SELECT id,email,plan,credits,role FROM users WHERE id=%s", (user_id,))
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


def require_admin(current_user: dict = Depends(get_current_user)):
    if current_user["role"] != "admin":
        raise HTTPException(status_code=403, detail="Acesso negado")
    return current_user


def deduct_credits(user_id: int, amount: int = 1):
    conn = get_connection()
    cur = conn.cursor()
    cur.execute("UPDATE users SET credits = credits - %s WHERE id = %s", (amount, user_id))
    conn.commit()
    cur.close()
    conn.close()


def apply_plan(user_id: int, plan: str):
    plan_data = PLANS[plan]
    conn = get_connection()
    cur = conn.cursor()
    if plan_data["type"] == "one_time":
        cur.execute("UPDATE users SET credits = credits + %s WHERE id = %s", (plan_data["credits"], user_id))
    else:
        cur.execute("UPDATE users SET plan = %s, credits = %s WHERE id = %s", (plan, plan_data["credits"], user_id))
    conn.commit()
    cur.close()
    conn.close()


def save_audio_history(user_id, project_name, texto, tom, audio_url, cloudinary_public_id, has_music=False):
    conn = get_connection()
    cur = conn.cursor()
    cur.execute("""
        INSERT INTO audio_history (user_id, project_name, texto, tom, audio_url, cloudinary_public_id, has_music)
        VALUES (%s, %s, %s, %s, %s, %s, %s)
    """, (user_id, project_name, texto, tom, audio_url, cloudinary_public_id, has_music))
    conn.commit()
    cur.close()
    conn.close()


def send_email(to: str, subject: str, html: str):
    if not RESEND_API_KEY:
        return
    requests.post(
        "https://api.resend.com/emails",
        headers={
            "Authorization": f"Bearer {RESEND_API_KEY}",
            "Content-Type": "application/json"
        },
        json={
            "from": "AI E&K Generator PRO <onboarding@resend.dev>",
            "to": [to],
            "subject": subject,
            "html": html
        }
    )


def prepare_text_for_tts(text: str) -> str:

    def convert_currency(match):
        value = match.group(0)
        value = value.replace("R$", "").replace("R$ ", "").strip()
        value = value.replace(".", "").replace(",", ".")
        try:
            amount = float(value)
            reais = int(amount)
            centavos = round((amount - reais) * 100)
            if centavos > 0:
                return f"{reais} reais e {centavos} centavos"
            return f"{reais} reais"
        except Exception:
            return match.group(0)

    def convert_percentage(match):
        return f"{match.group(1)} por cento"

    def convert_decimal(match):
        inteiro = match.group(1)
        decimal = match.group(2)
        return f"{inteiro} e {decimal}"

    def convert_thousands(match):
        return match.group(0).replace(".", "")

    # Converte valores monetarios primeiro
    text = re.sub(r"R\$\s?[\d.,]+", convert_currency, text)

    # Converte porcentagens
    text = re.sub(r"(\d+)%", convert_percentage, text)

    # Converte numeros com ponto de milhar
    text = re.sub(r"\d{1,3}(?:\.\d{3})+", convert_thousands, text)

    # Converte decimais com virgula ex: 9,50 -> nove e cinquenta
    text = re.sub(r"(\d+),(\d+)", convert_decimal, text)

    # Remove virgulas soltas entre numeros
    text = re.sub(r"(\d),(\d)", r"\1 \2", text)

    return text


def mix_audio(voice_bytes: bytes, music_bytes: bytes) -> bytes:
    voice = AudioSegment.from_mp3(io.BytesIO(voice_bytes))
    music = AudioSegment.from_file(io.BytesIO(music_bytes))

    # Total = intro 3s + voz + final 30s
    total_duration = len(voice) + 33000
    if len(music) < total_duration:
        loops = total_duration // len(music) + 1
        music = music * loops

    # Intro: musica em volume normal por 3 segundos
    music_intro = music[:3000].fade_in(500)

    # Durante a voz: musica bem baixa
    music_under_voice = music[3000:3000 + len(voice)] - 15

    # Final: musica volta ao volume normal por 30 segundos e fecha suavemente
    music_outro = music[3000 + len(voice):3000 + len(voice) + 30000]
    music_outro = music_outro + 8
    music_outro = music_outro.fade_out(5000)

    # Junta tudo
    background = music_intro + music_under_voice + music_outro

    # Voz entra depois do intro de 3 segundos
    silence = AudioSegment.silent(duration=3000)
    voice_with_delay = silence + voice

    # Mixagem final
    final = background.overlay(voice_with_delay)

    output = io.BytesIO()
    final.export(output, format="mp3")
    return output.getvalue()


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


@app.get("/voices")
def voices(current_user: dict = Depends(get_current_user)):
    plan = current_user["plan"]
    if current_user["role"] == "admin":
        plan = "premium"
    rules = PLAN_RULES.get(plan, PLAN_RULES["free"])
    allowed = rules["voices"]
    all_voices = [
        {"id": "promocional", "name": "Promocional"},
        {"id": "institucional", "name": "Institucional"},
        {"id": "calmo", "name": "Calmo"},
        {"id": "entusiasta", "name": "Entusiasta"},
        {"id": "neutro", "name": "Neutro"}
    ]
    return [{**v, "locked": v["id"] not in allowed} for v in all_voices]


@app.post("/auth/forgot-password")
def forgot_password(data: ForgotPasswordRequest):
    conn = get_connection()
    cur = conn.cursor()
    cur.execute("SELECT id, email FROM users WHERE email = %s", (data.email,))
    user = cur.fetchone()
    if not user:
        cur.close()
        conn.close()
        return {"message": "Se o email existir, voce recebera o link em breve"}
    user_id, email = user
    token = secrets.token_urlsafe(32)
    expires_at = datetime.utcnow() + timedelta(hours=1)
    cur.execute("INSERT INTO password_resets (user_id, token, expires_at) VALUES (%s, %s, %s)", (user_id, token, expires_at))
    conn.commit()
    cur.close()
    conn.close()
    reset_link = f"{FRONTEND_URL}/redefinir-senha?token={token}"
    send_email(
        to=email,
        subject="Redefinicao de senha - AI E&K Generator PRO",
        html=f"""
        <div style="font-family: Arial, sans-serif; max-width: 600px; margin: 0 auto;">
            <h2 style="color: #1a1a2e;">Redefinicao de senha</h2>
            <p>Voce solicitou a redefinicao da sua senha no AI E&K Generator PRO.</p>
            <a href="{reset_link}" style="display:inline-block;background:#0066ff;color:white;padding:12px 24px;border-radius:8px;text-decoration:none;font-weight:bold;margin:16px 0;">
                Redefinir minha senha
            </a>
            <p style="color:#666;font-size:13px;">Este link expira em 1 hora.</p>
        </div>
        """
    )
    return {"message": "Se o email existir, voce recebera o link em breve"}


@app.post("/auth/reset-password")
def reset_password(data: ResetPasswordRequest):
    conn = get_connection()
    cur = conn.cursor()
    cur.execute("SELECT id, user_id, expires_at, used FROM password_resets WHERE token = %s", (data.token,))
    reset = cur.fetchone()
    if not reset:
        raise HTTPException(status_code=400, detail="Token invalido")
    reset_id, user_id, expires_at, used = reset
    if used:
        raise HTTPException(status_code=400, detail="Token ja utilizado")
    if datetime.utcnow() > expires_at:
        raise HTTPException(status_code=400, detail="Token expirado. Solicite um novo link.")
    hashed = bcrypt.hashpw(data.new_password.encode(), bcrypt.gensalt()).decode()
    cur.execute("UPDATE users SET password_hash = %s WHERE id = %s", (hashed, user_id))
    cur.execute("UPDATE password_resets SET used = TRUE WHERE id = %s", (reset_id,))
    conn.commit()
    cur.close()
    conn.close()
    return {"message": "Senha redefinida com sucesso"}


@app.post("/support")
def create_support(data: SupportRequest, current_user: dict = Depends(get_current_user)):
    conn = get_connection()
    cur = conn.cursor()
    cur.execute("INSERT INTO support_tickets (user_id, nome, email, assunto, mensagem) VALUES (%s, %s, %s, %s, %s)",
        (current_user["id"], data.nome, data.email, data.assunto, data.mensagem))
    conn.commit()
    cur.close()
    conn.close()
    send_email(
        to=ADMIN_EMAIL,
        subject=f"[Suporte] {data.assunto} - {data.nome}",
        html=f"""
        <h2>Nova mensagem de suporte</h2>
        <p><b>Nome:</b> {data.nome}</p>
        <p><b>Email:</b> {data.email}</p>
        <p><b>Assunto:</b> {data.assunto}</p>
        <p><b>Mensagem:</b></p>
        <p>{data.mensagem}</p>
        <hr>
        <p>Responda para: <a href="mailto:{data.email}">{data.email}</a></p>
        """
    )
    return {"message": "Mensagem enviada com sucesso"}


@app.get("/admin/support")
def admin_support(admin: dict = Depends(require_admin)):
    conn = get_connection()
    cur = conn.cursor()
    cur.execute("SELECT id, nome, email, assunto, mensagem, status, created_at FROM support_tickets ORDER BY created_at DESC")
    rows = cur.fetchall()
    cur.close()
    conn.close()
    return [{"id": row[0], "nome": row[1], "email": row[2], "assunto": row[3], "mensagem": row[4], "status": row[5], "created_at": row[6].strftime("%d/%m/%Y %H:%M")} for row in rows]


@app.put("/admin/support/{ticket_id}")
def update_support_status(ticket_id: int, admin: dict = Depends(require_admin)):
    conn = get_connection()
    cur = conn.cursor()
    cur.execute("UPDATE support_tickets SET status = 'resolvido' WHERE id = %s", (ticket_id,))
    conn.commit()
    cur.close()
    conn.close()
    return {"message": "Ticket resolvido"}


@app.get("/admin/stats")
def admin_stats(admin: dict = Depends(require_admin)):
    conn = get_connection()
    cur = conn.cursor()
    cur.execute("SELECT COUNT(*) FROM users WHERE role != 'admin'")
    total_users = cur.fetchone()[0]
    cur.execute("SELECT COUNT(*) FROM audio_history")
    total_audios = cur.fetchone()[0]
    cur.execute("SELECT COALESCE(SUM(amount), 0) FROM payments WHERE status = 'approved'")
    total_revenue = cur.fetchone()[0]
    cur.execute("SELECT COUNT(*) FROM payments WHERE status = 'approved'")
    total_payments = cur.fetchone()[0]
    cur.execute("SELECT COUNT(*) FROM support_tickets WHERE status = 'aberto'")
    open_tickets = cur.fetchone()[0]
    cur.execute("""
        SELECT DATE(created_at), COALESCE(SUM(amount), 0)
        FROM payments WHERE status = 'approved'
        AND created_at >= NOW() - INTERVAL '30 days'
        GROUP BY DATE(created_at)
        ORDER BY DATE(created_at)
    """)
    revenue_chart = [{"date": str(row[0]), "value": float(row[1])} for row in cur.fetchall()]
    cur.close()
    conn.close()
    return {"total_users": total_users, "total_audios": total_audios, "total_revenue": float(total_revenue), "total_payments": total_payments, "open_tickets": open_tickets, "revenue_chart": revenue_chart}


@app.get("/admin/users")
def admin_users(admin: dict = Depends(require_admin)):
    conn = get_connection()
    cur = conn.cursor()
    cur.execute("SELECT id, email, plan, credits, role, created_at FROM users ORDER BY created_at DESC")
    rows = cur.fetchall()
    cur.close()
    conn.close()
    return [{"id": row[0], "email": row[1], "plan": row[2], "credits": row[3], "role": row[4], "created_at": row[5].strftime("%d/%m/%Y")} for row in rows]


@app.put("/admin/users/{user_id}")
def admin_update_user(user_id: int, data: UpdateUserRequest, admin: dict = Depends(require_admin)):
    conn = get_connection()
    cur = conn.cursor()
    if data.plan:
        cur.execute("UPDATE users SET plan = %s WHERE id = %s", (data.plan, user_id))
    if data.credits is not None:
        cur.execute("UPDATE users SET credits = %s WHERE id = %s", (data.credits, user_id))
    if data.role:
        cur.execute("UPDATE users SET role = %s WHERE id = %s", (data.role, user_id))
    conn.commit()
    cur.close()
    conn.close()
    return {"message": "Usuario atualizado"}


@app.get("/admin/payments")
def admin_payments(admin: dict = Depends(require_admin)):
    conn = get_connection()
    cur = conn.cursor()
    cur.execute("""
        SELECT p.id, u.email, p.plan, p.amount, p.status, p.created_at
        FROM payments p JOIN users u ON p.user_id = u.id
        ORDER BY p.created_at DESC LIMIT 100
    """)
    rows = cur.fetchall()
    cur.close()
    conn.close()
    return [{"id": row[0], "email": row[1], "plan": row[2], "amount": float(row[3]), "status": row[4], "created_at": row[5].strftime("%d/%m/%Y %H:%M")} for row in rows]


@app.get("/audio/history")
def get_audio_history(current_user: dict = Depends(get_current_user)):
    conn = get_connection()
    cur = conn.cursor()
    cur.execute("""
        SELECT id, project_name, texto, tom, audio_url, has_music, created_at
        FROM audio_history WHERE user_id = %s
        ORDER BY created_at DESC LIMIT 50
    """, (current_user["id"],))
    rows = cur.fetchall()
    cur.close()
    conn.close()
    return [{"id": row[0], "project_name": row[1], "texto": row[2], "tom": row[3], "audio_url": row[4], "has_music": row[5], "created_at": row[6].strftime("%d/%m/%Y %H:%M")} for row in rows]


@app.delete("/audio/history/{audio_id}")
def delete_audio(audio_id: int, current_user: dict = Depends(get_current_user)):
    conn = get_connection()
    cur = conn.cursor()
    cur.execute("SELECT cloudinary_public_id, user_id FROM audio_history WHERE id = %s", (audio_id,))
    row = cur.fetchone()
    if not row:
        raise HTTPException(status_code=404, detail="Audio nao encontrado")
    cloudinary_public_id, owner_id = row
    if owner_id != current_user["id"] and current_user["role"] != "admin":
        raise HTTPException(status_code=403, detail="Sem permissao")
    if cloudinary_public_id:
        try:
            cloudinary.uploader.destroy(cloudinary_public_id, resource_type="video")
        except Exception:
            pass
    cur.execute("DELETE FROM audio_history WHERE id = %s", (audio_id,))
    conn.commit()
    cur.close()
    conn.close()
    return {"message": "Audio excluido com sucesso"}


@app.post("/payment/create")
def create_payment(data: PaymentRequest, current_user: dict = Depends(get_current_user)):
    if data.plan not in PLANS:
        raise HTTPException(status_code=400, detail="Plano invalido")
    plan_data = PLANS[data.plan]
    idempotency_key = str(uuid.uuid4())
    headers = {"Authorization": f"Bearer {MP_ACCESS_TOKEN}", "Content-Type": "application/json", "X-Idempotency-Key": idempotency_key}
    payload = {
        "transaction_amount": float(plan_data["price"]),
        "description": plan_data["name"],
        "payment_method_id": data.payment_method,
        "payer": {"email": current_user["email"]},
        "metadata": {"user_id": str(current_user["id"]), "plan": data.plan}
    }
    if data.payment_method == "credit_card":
        if not data.token:
            raise HTTPException(status_code=400, detail="Token do cartao obrigatorio")
        payload["token"] = data.token
        payload["installments"] = data.installments or 1
        if data.issuer_id:
            payload["issuer_id"] = data.issuer_id
    response = requests.post("https://api.mercadopago.com/v1/payments", json=payload, headers=headers)
    result = response.json()
    if response.status_code not in [200, 201]:
        raise HTTPException(status_code=400, detail=result.get("message", "Erro ao criar pagamento"))
    conn = get_connection()
    cur = conn.cursor()
    cur.execute("INSERT INTO payments (user_id, mp_payment_id, plan, amount, status) VALUES (%s, %s, %s, %s, %s)",
        (current_user["id"], str(result["id"]), data.plan, plan_data["price"], result["status"]))
    conn.commit()
    cur.close()
    conn.close()
    if result["status"] == "approved":
        apply_plan(current_user["id"], data.plan)
    response_data = {"payment_id": result["id"], "status": result["status"], "plan": data.plan}
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
    response = requests.get(f"https://api.mercadopago.com/v1/payments/{payment_id}", headers=headers)
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
    cur.execute("UPDATE payments SET status = 'approved' WHERE mp_payment_id = %s", (str(payment_id),))
    conn.commit()
    cur.close()
    conn.close()
    apply_plan(int(user_id), plan)
    return {"status": "ok"}


@app.get("/payment/status/{payment_id}")
def payment_status(payment_id: str, current_user: dict = Depends(get_current_user)):
    headers = {"Authorization": f"Bearer {MP_ACCESS_TOKEN}"}
    response = requests.get(f"https://api.mercadopago.com/v1/payments/{payment_id}", headers=headers)
    result = response.json()
    return {"payment_id": payment_id, "status": result.get("status"), "status_detail": result.get("status_detail")}


@app.post("/register")
def register(user: UserCreate):
    hashed = bcrypt.hashpw(user.password.encode(), bcrypt.gensalt()).decode()
    conn = get_connection()
    cur = conn.cursor()
    try:
        cur.execute("INSERT INTO users (email,password_hash,plan,credits,role) VALUES (%s,%s,'free',10,'user')", (user.email, hashed))
        conn.commit()
    except Exception as e:
        raise HTTPException(status_code=400, detail=str(e))
    finally:
        cur.close()
        conn.close()
    return {"message": "Usuario criado"}


@app.post("/login")
def login(data: LoginRequest):
    conn = get_connection()
    cur = conn.cursor()
    cur.execute("SELECT id,password_hash,role FROM users WHERE email=%s", (data.email,))
    user = cur.fetchone()
    cur.close()
    conn.close()
    if not user:
        raise HTTPException(status_code=400, detail="Usuario nao encontrado")
    user_id, password_hash, role = user
    if not bcrypt.checkpw(data.password.encode(), password_hash.encode()):
        raise HTTPException(status_code=400, detail="Senha invalida")
    token = create_access_token({"user_id": user_id, "role": role})
    return {"access_token": token, "token_type": "bearer"}


@app.get("/audio/test")
def test_audio():
    voice_id = VOICES["calmo"]
    url = f"https://api.elevenlabs.io/v1/text-to-speech/{voice_id}"
    headers = {"xi-api-key": ELEVEN_API_KEY, "Content-Type": "application/json", "Accept": "audio/mpeg"}
    payload = {"text": "Teste direto de voz funcionando", "model_id": "eleven_multilingual_v2", "language_code": "pt"}
    response = requests.post(url, json=payload, headers=headers)
    if response.status_code != 200:
        raise HTTPException(status_code=500, detail=response.text)
    return Response(content=response.content, media_type="audio/mpeg")


@app.post("/audio/generate")
def generate_audio(data: AudioRequest, current_user: dict = Depends(get_current_user)):
    plan = current_user["plan"]
    is_admin = current_user["role"] == "admin"

    if not is_admin:
        if current_user["credits"] <= 0:
            raise HTTPException(status_code=402, detail="Creditos esgotados. Faca upgrade do seu plano para continuar.")
        rules = PLAN_RULES.get(plan, PLAN_RULES["free"])
        if data.tom not in rules["voices"]:
            raise HTTPException(status_code=403, detail="Voz nao disponivel no seu plano.")
        if len(data.texto) > rules["max_chars"]:
            raise HTTPException(status_code=403, detail="Texto excede o limite de caracteres do seu plano.")

    voice_id = VOICES.get(data.tom, VOICES["calmo"])
    url = f"https://api.elevenlabs.io/v1/text-to-speech/{voice_id}"
    headers = {"xi-api-key": ELEVEN_API_KEY, "Content-Type": "application/json", "Accept": "audio/mpeg"}
    texto_preparado = prepare_text_for_tts(data.texto)
    payload = {"text": texto_preparado, "model_id": "eleven_multilingual_v2", "language_code": "pt"}

    response = requests.post(url, json=payload, headers=headers)
    if response.status_code != 200:
        raise HTTPException(status_code=500, detail=response.text)

    public_id = f"audio_{current_user['id']}_{uuid.uuid4().hex[:8]}"
    upload_result = cloudinary.uploader.upload(
        response.content, resource_type="video", public_id=public_id, folder="ek_generator", format="mp3"
    )
    audio_url = upload_result.get("secure_url")

    if not is_admin:
        deduct_credits(current_user["id"], 1)

    save_audio_history(current_user["id"], data.project_name, data.texto, data.tom, audio_url, upload_result.get("public_id"), False)

    return {"audio_url": audio_url, "message": "Audio gerado com sucesso"}


@app.post("/audio/generate-with-music")
async def generate_audio_with_music(
    texto: str = Form(...),
    tom: str = Form("calmo"),
    project_name: str = Form("Sem titulo"),
    music_file: UploadFile = File(...),
    credentials: HTTPAuthorizationCredentials = Depends(security)
):
    token = credentials.credentials
    try:
        payload = jwt.decode(token, SECRET_KEY, algorithms=[ALGORITHM])
        user_id = payload.get("user_id")
    except JWTError:
        raise HTTPException(status_code=401, detail="Token invalido")

    conn = get_connection()
    cur = conn.cursor()
    cur.execute("SELECT id,email,plan,credits,role FROM users WHERE id=%s", (user_id,))
    user = cur.fetchone()
    cur.close()
    conn.close()

    if not user:
        raise HTTPException(status_code=401)

    current_user = {"id": user[0], "email": user[1], "plan": user[2], "credits": user[3], "role": user[4]}
    is_admin = current_user["role"] == "admin"
    plan = current_user["plan"]

    if not is_admin:
        if current_user["credits"] < 3:
            raise HTTPException(status_code=402, detail="Creditos insuficientes. A mixagem com musica custa 3 creditos.")
        rules = PLAN_RULES.get(plan, PLAN_RULES["free"])
        if tom not in rules["voices"]:
            raise HTTPException(status_code=403, detail="Voz nao disponivel no seu plano.")
        if len(texto) > rules["max_chars"]:
            raise HTTPException(status_code=403, detail="Texto excede o limite de caracteres do seu plano.")

    voice_id = VOICES.get(tom, VOICES["calmo"])
    url = f"https://api.elevenlabs.io/v1/text-to-speech/{voice_id}"
    headers = {"xi-api-key": ELEVEN_API_KEY, "Content-Type": "application/json", "Accept": "audio/mpeg"}
    texto_preparado = prepare_text_for_tts(texto)
    voice_payload = {"text": texto_preparado, "model_id": "eleven_multilingual_v2", "language_code": "pt"}

    voice_response = requests.post(url, json=voice_payload, headers=headers)
    if voice_response.status_code != 200:
        raise HTTPException(status_code=500, detail=voice_response.text)

    music_bytes = await music_file.read()
    final_audio = mix_audio(voice_response.content, music_bytes)

    public_id = f"audio_music_{current_user['id']}_{uuid.uuid4().hex[:8]}"
    upload_result = cloudinary.uploader.upload(
        final_audio, resource_type="video", public_id=public_id, folder="ek_generator", format="mp3"
    )
    audio_url = upload_result.get("secure_url")

    if not is_admin:
        deduct_credits(current_user["id"], 3)

    save_audio_history(current_user["id"], project_name, texto, tom, audio_url, upload_result.get("public_id"), True)

    return {"audio_url": audio_url, "message": "Audio com musica gerado com sucesso"}

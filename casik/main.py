from fastapi import FastAPI, HTTPException, Request
from fastapi.staticfiles import StaticFiles
from fastapi.responses import HTMLResponse, RedirectResponse
from authlib.integrations.starlette_client import OAuth
import hashlib
import hmac
import sqlite3
import os

app = FastAPI()

# OAuth для VK
oauth = OAuth()
oauth.register(
    name='vk',
    server_metadata_url='https://oauth.vk.com/.well-known/openid-configuration',
    access_token_url='https://oauth.vk.com/access_token',
    authorize_url='https://oauth.vk.com/authorize',
    client_kwargs={
        'scope': 'email'
    },
    client_id='YOUR_VK_APP_ID',
    client_secret='YOUR_VK_APP_SECRET'
)

# Подключение к SQLite
conn = sqlite3.connect("casino.db", check_same_thread=False)
cursor = conn.cursor()

# Создание таблиц
cursor.execute("""
    CREATE TABLE IF NOT EXISTS users (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        telegram_id TEXT UNIQUE,
        vk_id TEXT UNIQUE,
        username TEXT,
        balance REAL DEFAULT 100.0,
        email TEXT DEFAULT '',
        created_at DATETIME DEFAULT CURRENT_TIMESTAMP
    )
""")
conn.commit()

# Telegram Bot Token (замените на свой)
TELEGRAM_BOT_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN", "YOUR_BOT_TOKEN_HERE")

def check_telegram_login_auth(data):
    received_hash = data.pop('hash', None)
    if not received_hash:
        return False

    sorted_data = sorted(data.items())
    data_check_string = "\n".join(f"{k}={v}" for k, v in sorted_data)

    secret_key = hashlib.sha256(TELEGRAM_BOT_TOKEN.encode()).digest()
    calculated_hash = hmac.new(secret_key, data_check_string.encode(), hashlib.sha256).hexdigest()

    return hmac.compare_digest(calculated_hash, received_hash)

# Авторизация через Telegram Web App
@app.post("/api/auth/telegram-webapp")
def auth_telegram_webapp(request: Request):
    form_data = dict(request.query_params)
    if not check_telegram_login_auth(form_data):
        raise HTTPException(status_code=400, detail="Invalid Telegram login auth")

    telegram_id = form_data['id']
    username = form_data.get('first_name', 'Unknown')
    email = form_data.get('email', '')

    cursor.execute("SELECT id, balance FROM users WHERE telegram_id = ?", (telegram_id,))
    user = cursor.fetchone()
    if user:
        user_id = user[0]
        balance = user[1]
    else:
        cursor.execute(
            "INSERT INTO users (telegram_id, username, email) VALUES (?, ?, ?)",
            (telegram_id, username, email)
        )
        conn.commit()
        user_id = cursor.lastrowid
        balance = 100.0

    # Возвращаем JSON вместо редиректа (для Web App)
    return {"user_id": user_id, "balance": balance, "username": username, "email": email}

# Авторизация через VK
@app.get("/login/vk")
async def login_vk(request: Request):
    redirect_uri = request.url_for('auth_vk')
    return await oauth.vk.authorize_redirect(request, redirect_uri)

@app.route('/auth/vk', methods=['GET'])
async def auth_vk(request: Request):
    token = await oauth.vk.authorize_access_token(request)
    user_info = token.get('user_info')

    vk_id = str(user_info['id'])
    username = f"{user_info.get('first_name', '')} {user_info.get('last_name', '')}".strip()
    email = user_info.get('email', '')

    cursor.execute("SELECT id, balance FROM users WHERE vk_id = ?", (vk_id,))
    user = cursor.fetchone()
    if user:
        user_id = user[0]
        balance = user[1]
    else:
        cursor.execute(
            "INSERT INTO users (vk_id, username, email) VALUES (?, ?, ?)",
            (vk_id, username, email)
        )
        conn.commit()
        user_id = cursor.lastrowid
        balance = 100.0

    redirect_url = f"/home.html?user_id={user_id}"
    return RedirectResponse(url=redirect_url, status_code=302)

@app.get("/api/balance/{user_id}")
def get_balance(user_id: int):
    cursor.execute("SELECT balance FROM users WHERE id = ?", (user_id,))
    user = cursor.fetchone()
    if not user:
        raise HTTPException(status_code=404, detail="User not found")
    return {"balance": user[0]}

@app.get("/api/profile/{user_id}")
def get_profile(user_id: int):
    cursor.execute("SELECT id, username, balance, email, created_at FROM users WHERE id = ?", (user_id,))
    user = cursor.fetchone()
    if not user:
        raise HTTPException(status_code=404, detail="User not found")
    return {
        "id": user[0],
        "username": user[1],
        "balance": user[2],
        "email": user[3],
        "created_at": user[4]
    }

# Подключаем статику
app.mount("/static", StaticFiles(directory="static"), name="static")
app.mount("/", StaticFiles(directory="static", html=True), name="static")
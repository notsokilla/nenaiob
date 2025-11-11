from fastapi import FastAPI, HTTPException, Request
from fastapi.staticfiles import StaticFiles
from fastapi.responses import HTMLResponse, RedirectResponse
import hashlib
import hmac
import sqlite3
import os

if __name__ == "__main__":
    port = int(os.environ.get("PORT", 8000))
    import uvicorn
    uvicorn.run("main:app", host="0.0.0.0", port=port)

app = FastAPI()

# Подключение к SQLite
conn = sqlite3.connect("casino.db", check_same_thread=False)
cursor = conn.cursor()

# Создание таблиц
cursor.execute("""
    CREATE TABLE IF NOT EXISTS users (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        telegram_id TEXT UNIQUE,
        username TEXT,
        balance REAL DEFAULT 100.0,
        email TEXT DEFAULT '',
        created_at DATETIME DEFAULT CURRENT_TIMESTAMP
    )
""")
conn.commit()

# Telegram Bot Token (замените на свой)
TELEGRAM_BOT_TOKEN = "8501831434:AAE1Mbfjc97nZD0Y4IshYqdgXdlvUn7_J2o"

def check_telegram_login_auth(data):
    received_hash = data.pop('hash', None)
    if not received_hash:
        return False

    sorted_data = sorted(data.items())
    data_check_string = "\n".join(f"{k}={v}" for k, v in sorted_data)

    secret_key = hashlib.sha256(TELEGRAM_BOT_TOKEN.encode()).digest()
    calculated_hash = hmac.new(secret_key, data_check_string.encode(), hashlib.sha256).hexdigest()

    return hmac.compare_digest(calculated_hash, received_hash)

# Авторизация через Telegram (теперь GET)
@app.get("/api/auth/telegram-login")
def auth_telegram_login(request: Request):
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
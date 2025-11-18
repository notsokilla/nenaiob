from fastapi import FastAPI, HTTPException, Request
from fastapi.staticfiles import StaticFiles
from fastapi.responses import HTMLResponse, RedirectResponse
import hashlib
import hmac
import sqlite3
import os
from sqlalchemy import create_engine, Column, Integer, String, Float
from sqlalchemy.orm import sessionmaker
from sqlalchemy.ext.declarative import declarative_base

app = FastAPI()

# Подключение к PostgreSQL
DATABASE_URL = os.getenv("DATABASE_URL")
if DATABASE_URL is None:
    raise ValueError("DATABASE_URL не установлен")

engine = create_engine(DATABASE_URL)
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)
Base = declarative_base()

# Модель пользователя
class User(Base):
    __tablename__ = "users"

    id = Column(Integer, primary_key=True, index=True)
    telegram_id = Column(String, unique=True, index=True)
    username = Column(String)
    balance = Column(Float, default=100.0)
    email = Column(String, default="")

# Создание таблиц
Base.metadata.create_all(bind=engine)

# Telegram Bot Token (замените на свой)
TELEGRAM_BOT_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN")
if TELEGRAM_BOT_TOKEN is None:
    raise ValueError("TELEGRAM_BOT_TOKEN не установлен")

def check_telegram_login_auth(data):
    received_hash = data.pop('hash', None)
    if not received_hash:
        return False

    sorted_data = sorted(data.items())
    data_check_string = "\n".join(f"{k}={v}" for k, v in sorted_data)

    secret_key = hashlib.sha256(TELEGRAM_BOT_TOKEN.encode()).digest()
    calculated_hash = hmac.new(secret_key, data_check_string.encode(), hashlib.sha256).hexdigest()

    return hmac.compare_digest(calculated_hash, received_hash)

# Авторизация через Telegram
@app.get("/api/auth/telegram-login")
def auth_telegram_login(request: Request):
    form_data = dict(request.query_params)
    if not check_telegram_login_auth(form_data):
        raise HTTPException(status_code=400, detail="Invalid Telegram login auth")

    telegram_id = form_data['id']
    username = form_data.get('first_name', 'Unknown')
    email = form_data.get('email', '')

    db = SessionLocal()
    user = db.query(User).filter(User.telegram_id == telegram_id).first()
    if user:
        user_id = user.id
        balance = user.balance
    else:
        new_user = User(telegram_id=telegram_id, username=username, email=email)
        db.add(new_user)
        db.commit()
        user_id = new_user.id
        balance = new_user.balance

    db.close()

    redirect_url = f"/home.html?user_id={user_id}"
    return RedirectResponse(url=redirect_url, status_code=302)

# Эндпоинт для игр
@app.get("/game/{game_name}")
def game_page(game_name: str):
    # Здесь можно добавить логику для конкретной игры
    return HTMLResponse(content=f"""
        <html>
            <head>
                <title>Игра {game_name}</title>
                <script src="https://cdn.tailwindcss.com"></script>
                <style>body {{ background: #0f0f13; color: white; font-family: 'Segoe UI', sans-serif; }}</style>
            </head>
            <body class="p-8">
                <h1 class="text-3xl font-bold">Вы выбрали игру: {game_name}</h1>
                <p class="mt-4">Это место для  игры с писюном.</p>
                <button onclick="window.location.href='/home.html'" class="mt-4 px-4 py-2 bg-blue-600 text-white rounded">Назад к играм</button>
            </body>
        </html>
    """)

@app.get("/api/balance/{user_id}")
def get_balance(user_id: int):
    db = SessionLocal()
    user = db.query(User).filter(User.id == user_id).first()
    if not user:
        raise HTTPException(status_code=404, detail="User not found")
    db.close()
    return {"balance": user.balance}

@app.get("/api/profile/{user_id}")
def get_profile(user_id: int):
    db = SessionLocal()
    user = db.query(User).filter(User.id == user_id).first()
    if not user:
        raise HTTPException(status_code=404, detail="User not found")
    db.close()
    return {
        "id": user.id,
        "username": user.username,
        "balance": user.balance,
        "email": user.email,
    }

# Подключаем статику
app.mount("/static", StaticFiles(directory="static"), name="static")
app.mount("/", StaticFiles(directory="static", html=True), name="static")

# Запуск сервера (только если файл запускается напрямую)
if __name__ == "__main__":
    import uvicorn
    port = int(os.environ.get("PORT", 10000))
    uvicorn.run(app, host="0.0.0.0", port=port)
from fastapi import FastAPI, HTTPException, Request
from fastapi.staticfiles import StaticFiles
from fastapi.responses import HTMLResponse, RedirectResponse
import hashlib
import hmac
import os
from sqlalchemy import create_engine, Column, Integer, String, Float
from sqlalchemy.ext.declarative import declarative_base
from sqlalchemy.orm import sessionmaker

app = FastAPI()

# Подключение к PostgreSQL
DATABASE_URL = os.getenv("DATABASE_URL", "postgresql://users_nenaiob_user:4oYI56V3u9npNiNGNFko5PjJvN3YVGRa@dpg-d49s7kruibrs73c2idt0-a.frankfurt-postgres.render.com/users_nenaiob")

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
TELEGRAM_BOT_TOKEN = os.getenv("8501831434:AAE1Mbfjc97nZD0Y4IshYqdgXdlvUn7_J2o")
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
from fastapi import FastAPI, HTTPException, Request
from fastapi.staticfiles import StaticFiles
from fastapi.responses import HTMLResponse, RedirectResponse
import hashlib
import hmac
import os
from sqlalchemy import create_engine, Column, Integer, String, Float, DateTime
from sqlalchemy.orm import sessionmaker
from sqlalchemy.ext.declarative import declarative_base
from datetime import datetime
import stripe

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

# Модель пополнений
class Deposit(Base):
    __tablename__ = "deposits"

    id = Column(Integer, primary_key=True, index=True)
    user_id = Column(Integer, index=True)
    amount = Column(Float)
    method = Column(String)
    status = Column(String, default="pending")
    created_at = Column(DateTime, default=datetime.utcnow)

# Создание таблиц
Base.metadata.create_all(bind=engine)

# Telegram Bot Token (замените на свой)
TELEGRAM_BOT_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN")
if TELEGRAM_BOT_TOKEN is None:
    raise ValueError("TELEGRAM_BOT_TOKEN не установлен")

# Stripe Secret Key (замените на свой)
STRIPE_SECRET_KEY = os.getenv("STRIPE_SECRET_KEY")
if STRIPE_SECRET_KEY is None:
    raise ValueError("STRIPE_SECRET_KEY не установлен")

stripe.api_key = STRIPE_SECRET_KEY

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

    redirect_url = f"/deposit.html?user_id={user_id}"
    return RedirectResponse(url=redirect_url, status_code=302)

# Эндпоинт для пополнения баланса
@app.post("/api/deposit/{user_id}")
def deposit_balance(user_id: int, amount: float, method: str):
    db = SessionLocal()
    user = db.query(User).filter(User.id == user_id).first()
    if not user:
        raise HTTPException(status_code=404, detail="User not found")

    # Создаём сессию Stripe Checkout
    try:
        session = stripe.checkout.Session.create(
            payment_method_types=['card'],
            line_items=[{
                'price_data': {
                    'currency': 'usd',
                    'product_data': {
                        'name': 'Пополнение баланса',
                    },
                    'unit_amount': int(amount * 100),  # в центах
                },
                'quantity': 1,
            }],
            mode='payment',
            success_url=f'https://your-site.com/success?session_id={{CHECKOUT_SESSION_ID}}',
            cancel_url='https://your-site.com/cancel',
        )

        # Сохраняем попытку пополнения
        deposit = Deposit(user_id=user_id, amount=amount, method=method, status="pending")
        db.add(deposit)
        db.commit()

        db.close()

        return {"session_id": session.id, "url": session.url}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

# Эндпоинт для проверки статуса платежа
@app.get("/api/payment-status")
def payment_status(session_id: str):
    try:
        session = stripe.checkout.Session.retrieve(session_id)

        if session.payment_status == "paid":
            # Обновляем статус пополнения
            db = SessionLocal()
            deposit = db.query(Deposit).filter(Deposit.status == "pending", Deposit.id == session_id).first()
            if deposit:
                deposit.status = "completed"
                user = db.query(User).filter(User.id == deposit.user_id).first()
                if user:
                    user.balance += deposit.amount
                db.commit()
            db.close()

            return {"status": "paid", "balance": user.balance}
        else:
            return {"status": "not_paid"}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

# Подключаем статику
app.mount("/static", StaticFiles(directory="static"), name="static")
app.mount("/", StaticFiles(directory="static", html=True), name="static")

# Запуск сервера (только если файл запускается напрямую)
if __name__ == "__main__":
    import uvicorn
    port = int(os.environ.get("PORT", 10000))
    uvicorn.run(app, host="0.0.0.0", port=port)
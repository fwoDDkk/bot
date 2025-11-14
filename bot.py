import asyncio
import sqlite3
import secrets
import aiohttp
import hmac
import hashlib
import random
import string
from aiogram import Bot, Dispatcher, types, Router, F
from aiogram.filters import Command
from aiogram.types import (
    InlineKeyboardMarkup,
    InlineKeyboardButton,
    WebAppInfo,
    LabeledPrice,
    PreCheckoutQuery,
)

# =========================
# 🔧 CONFIG
# =========================
API_TOKEN = "8301527148:AAE7UDyJXFg4-db55P8nKeVoxw06gqnHjvo"   # ⬅️ ВСТАВ СВІЙ
PAYMENT_PROVIDER_TOKEN = ""     # Stars provider
WEB_URL = "https://vefefwewf.vercel.app/"
BACKEND_URL = "https://oneback-d62p.onrender.com"

MANAGER_USERNAME = "StarcManager"
MANAGER_CHAT_ID = 8299885208   # якщо треба, заміни

# --- Обов’язкова підписка ---
CHANNEL_ID = -1003017246760      # ID каналу
CHANNEL_LINK = "https://t.me/StarcSeller"  # посилання на канал


# =========================
# ⚙ INIT
# =========================
bot = Bot(token=API_TOKEN)
dp = Dispatcher()
router = Router()


# =========================
# 💾 DATABASE
# =========================
def init_db():
    conn = sqlite3.connect("users.db")
    cur = conn.cursor()
    cur.execute("""
        CREATE TABLE IF NOT EXISTS users (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            tg_id INTEGER UNIQUE,
            username TEXT,
            first_name TEXT,
            last_name TEXT,
            token TEXT
        )
    """)
    conn.commit()
    conn.close()


def add_user(tg_id, username, first_name, last_name, token):
    conn = sqlite3.connect("users.db")
    cur = conn.cursor()
    cur.execute("""
        INSERT OR REPLACE INTO users (tg_id, username, first_name, last_name, token)
        VALUES (?, ?, ?, ?, ?)
    """, (tg_id, username, first_name, last_name, token))
    conn.commit()
    conn.close()


# =========================
# 🔐 HASH VERIFY (як у бекенді)
# =========================
def create_tg_hash(data: dict, bot_token: str) -> str:
    check_string = "\n".join(
        f"{k}={v}" for k, v in sorted(data.items()) if k != "hash"
    )
    secret = hashlib.sha256(bot_token.encode()).digest()
    return hmac.new(secret, check_string.encode(), hashlib.sha256).hexdigest()


# =========================
# 🌐 SEND USER DATA TO BACKEND
# =========================
async def send_to_backend(data: dict):
    try:
        async with aiohttp.ClientSession() as session:
            async with session.post(
                f"{BACKEND_URL}/api/auth/telegram",
                json=data,
                headers={"Content-Type": "application/json"},
                timeout=10
            ) as resp:
                print("Backend:", resp.status, await resp.text())
    except Exception as e:
        print("❌ Backend send error:", e)


# =========================
# 🔍 CHECK SUBSCRIPTION
# =========================
async def is_subscribed(user_id: int) -> bool:
    try:
        member = await bot.get_chat_member(CHANNEL_ID, user_id)
        return member.status in ["member", "administrator", "creator"]
    except:
        return False


# =========================
# 🚀 OPEN WEBAPP FUNCTION
# =========================
async def open_webapp(message: types.Message):
    user = message.from_user
    tg_id = user.id
    token = secrets.token_hex(16)

    add_user(tg_id, user.username or "", user.first_name or "", user.last_name or "", token)

    # get user avatar
    photo_url = ""
    photos = await bot.get_user_profile_photos(tg_id, limit=1)
    if photos.total_count > 0:
        file = await bot.get_file(photos.photos[0][0].file_id)
        photo_url = f"https://api.telegram.org/file/bot{API_TOKEN}/{file.file_path}"

    # data for backend
    data = {
        "id": tg_id,
        "first_name": user.first_name or "",
        "last_name": user.last_name or "",
        "username": user.username or "",
        "photo_url": photo_url,
        "auth_date": int(message.date.timestamp()),
    }
    data["hash"] = create_tg_hash(data, API_TOKEN)

    asyncio.create_task(send_to_backend(data))

    kb = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="Увійти ✔", web_app=WebAppInfo(url=WEB_URL))]
    ])

    await message.answer("👋 Вітаю! Натисни кнопку нижче 👇", reply_markup=kb)


# =========================
# 🧭 START WITH SUB CHECK
# =========================
@router.message(Command("start"))
async def start_cmd(message: types.Message):
    user_id = message.from_user.id

    # --- check subscription ---
    sub = await is_subscribed(user_id)
    if not sub:
        kb = InlineKeyboardMarkup(inline_keyboard=[
            [InlineKeyboardButton(text="📢 Підписатися на канал", url=CHANNEL_LINK)],
            [InlineKeyboardButton(text="✅ Я підписався", callback_data="check_sub")]
        ])
        return await message.answer(
            "⭐️Щоб користуватися сервісом, підпишись на наш канал з відгуками.💰\n\n"
            "✅ Після підписки натисни кнопку «Я підписався»",
            reply_markup=kb
        )

    # --- open WebApp (user is subscribed) ---
    await open_webapp(message)


# =========================
# 🔁 RECHECK SUBSCRIPTION
# =========================
@router.callback_query(F.data == "check_sub")
async def recheck_subscription(callback: types.CallbackQuery):
    user_id = callback.from_user.id

    if not await is_subscribed(user_id):
        return await callback.answer("❌ Ви ще не підписалися!", show_alert=True)

    await callback.message.edit_text("🎉 Дякую за підписку! Завантажую…")
    await open_webapp(callback.message)


# =========================
# 💫 TELEGRAM STARS PAYMENT
# =========================
async def send_invoice(user_id, title, desc, amount, payload):
    prices = [LabeledPrice(label=title, amount=amount)]
    await bot.send_invoice(
        chat_id=user_id,
        title=title,
        description=desc,
        payload=payload,
        provider_token=PAYMENT_PROVIDER_TOKEN,
        currency="XTR",
        prices=prices
    )


@router.pre_checkout_query()
async def pre_checkout(pre: PreCheckoutQuery):
    await bot.answer_pre_checkout_query(pre.id, ok=True)


@router.message(F.content_type == "successful_payment")
async def successful_payment(message: types.Message):
    payment = message.successful_payment
    order_id = ''.join(random.choices(string.ascii_uppercase + string.digits, k=6))
    amount = payment.total_amount

    text = (
        f"✅ <b>Оплата успішна!</b>\n"
        f"💳 {amount:.0f}⭐\n"
        f"🧾 Замовлення: <code>{order_id}</code>\n\n"
        f"Зв’яжіться з менеджером 👇"
    )

    manager_msg = (
        f"Привіт! Я оплатив замовлення №{order_id} "
        f"на суму {amount:.0f}⭐"
    )

    manager_url = f"https://t.me/{MANAGER_USERNAME}?start={manager_msg.replace(' ', '%20')}"

    kb = InlineKeyboardMarkup(
        inline_keyboard=[[InlineKeyboardButton(text="💬 Менеджер", url=manager_url)]]
    )

    await message.answer(text, parse_mode="HTML", reply_markup=kb)


# =========================
# 🌐 WEBAPP DATA
# =========================
@router.message(F.web_app_data)
async def webapp_data_handler(message: types.Message):
    print("WEBAPP DATA:", message.web_app_data.data)


# =========================
# ▶️ START BOT
# =========================
async def main():
    print("🤖 Bot is running...")
    init_db()
    dp.include_router(router)
    await bot.delete_webhook(drop_pending_updates=True)
    await dp.start_polling(bot)


if __name__ == "__main__":
    asyncio.run(main())





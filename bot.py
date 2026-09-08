import asyncio
import logging
from datetime import datetime
from aiogram import Bot, Dispatcher, types
from aiogram.types import InlineKeyboardMarkup, InlineKeyboardButton
from aiogram.filters import Command
import aiohttp
import json

from config import BOT_TOKEN, ADMIN_ID, XRAY_API, XRAY_USERNAME, XRAY_PASSWORD, SERVER_IP
from database import Database

bot = Bot(token=BOT_TOKEN)
dp = Dispatcher()
db = Database()

logging.basicConfig(level=logging.INFO)

async def create_vpn_key(user_id):
    try:
        async with aiohttp.ClientSession() as session:
            login_data = {
                "username": XRAY_USERNAME,
                "password": XRAY_PASSWORD
            }
            async with session.post(f"{XRAY_API}/login", json=login_data) as resp:
                if resp.status != 200:
                    return None
                token_data = await resp.json()
                token = token_data.get('accessToken')
                if not token:
                    return None
            
            headers = {"Authorization": f"Bearer {token}"}
            async with session.get(f"{XRAY_API}/list", headers=headers) as resp:
                data = await resp.json()
                if not data.get('success'):
                    return None
                inbounds = data.get('obj', [])
                if not inbounds:
                    return None
                inbound_id = inbounds[0].get('id')
                inbound_port = inbounds[0].get('port')
                inbound_protocol = inbounds[0].get('protocol')
            
            client_id = f"user_{user_id}_{int(datetime.now().timestamp())}"
            
            client_data = {
                "id": inbound_id,
                "settings": json.dumps({
                    "clients": [{
                        "id": client_id,
                        "email": f"user_{user_id}@vpn.com",
                        "limitIp": 2,
                        "totalGB": 0,
                        "expiryTime": 0,
                        "enable": True
                    }]
                })
            }
            
            async with session.post(
                f"{XRAY_API}/addClient",
                headers=headers,
                json=client_data
            ) as resp:
                if resp.status != 200:
                    return None
                result = await resp.json()
                if not result.get('success'):
                    return None
            
            if inbound_protocol == "vless":
                link = f"vless://{client_id}@{SERVER_IP}:{inbound_port}?security=reality&encryption=none&type=tcp&flow=xtls-rprx-vision&sni=www.microsoft.com#VPN_BOT"
            else:
                link = f"Ссылка для {inbound_protocol} пока не настроена"
            
            db.save_vpn_link(user_id, link)
            return link
                
    except Exception as e:
        logging.error(f"Ошибка: {e}")
        return None

def main_menu():
    keyboard = InlineKeyboardMarkup(row_width=2)
    keyboard.add(
        InlineKeyboardButton("🎁 Пробный период", callback_data="trial"),
        InlineKeyboardButton("💰 Купить VPN", callback_data="buy")
    )
    keyboard.add(
        InlineKeyboardButton("📊 Мой статус", callback_data="status"),
        InlineKeyboardButton("🔗 Получить ссылку", callback_data="get_link")
    )
    keyboard.add(
        InlineKeyboardButton("🆘 Помощь", callback_data="help")
    )
    return keyboard

def buy_menu():
    keyboard = InlineKeyboardMarkup(row_width=2)
    keyboard.add(
        InlineKeyboardButton("📅 1 месяц - 500₽", callback_data="pay_30"),
        InlineKeyboardButton("📅 3 месяца - 1200₽", callback_data="pay_90")
    )
    keyboard.add(
        InlineKeyboardButton("📅 6 месяцев - 2000₽", callback_data="pay_180"),
        InlineKeyboardButton("📅 1 год - 3500₽", callback_data="pay_365")
    )
    keyboard.add(InlineKeyboardButton("◀️ Назад", callback_data="back"))
    return keyboard

@dp.message(Command("start"))
async def start_command(message: types.Message):
    user_id = message.from_user.id
    username = message.from_user.username or "NoUsername"
    db.add_user(user_id, username)
    await message.answer(
        f"👋 Привет, {message.from_user.first_name}!\n\nЯ бот для выдачи VPN.\nВыбери действие:",
        reply_markup=main_menu()
    )

@dp.message(Command("admin"))
async def admin_panel(message: types.Message):
    if message.from_user.id != ADMIN_ID:
        await message.answer("⛔ Доступ запрещен")
        return
    total, active = db.get_stats()
    await message.answer(
        f"📊 Админ-панель\n\n👥 Всего: {total}\n✅ Активных: {active}\n❌ Неактивных: {total - active}"
    )

@dp.callback_query(lambda c: c.data == "trial")
async def trial_callback(callback: types.CallbackQuery):
    user_id = callback.from_user.id
    user = db.get_user(user_id)
    if not user:
        await callback.message.answer("❌ Ошибка. Напишите /start")
        await callback.answer()
        return
    if user[3] == 1:
        await callback.message.answer("❌ Вы уже использовали пробный период!")
        await callback.answer()
        return
    db.activate_trial(user_id)
    link = await create_vpn_key(user_id)
    if link:
        await callback.message.answer(
            f"✅ Пробный период на 3 дня активирован!\n\n🔗 Твоя ссылка:\n`{link}`\n\n📱 Скачай V2RayNG (Android) или Nekoray (PC) и импортируй эту ссылку.",
            parse_mode="Markdown",
            reply_markup=main_menu()
        )
    else:
        await callback.message.answer("❌ Ошибка. Напишите @admin")
    await callback.answer()

@dp.callback_query(lambda c: c.data == "get_link")
async def get_link_callback(callback: types.CallbackQuery):
    user_id = callback.from_user.id
    is_active, msg = db.check_subscription(user_id)
    if not is_active:
        await callback.message.answer(f"❌ {msg}\n\nКупи подписку или активируй пробный период.", reply_markup=main_menu())
        await callback.answer()
        return
    user = db.get_user(user_id)
    link = user[4]
    if not link:
        link = await create_vpn_key(user_id)
        if not link:
            await callback.message.answer("❌ Ошибка. Напишите @admin")
            await callback.answer()
            return
    await callback.message.answer(f"✅ Твоя ссылка активна!\n\n🔗 `{link}`\n\n📊 {msg}", parse_mode="Markdown", reply_markup=main_menu())
    await callback.answer()

@dp.callback_query(lambda c: c.data == "buy")
async def buy_callback(callback: types.CallbackQuery):
    await callback.message.edit_text(
        "💳 Выбери тариф:\n\n🔹 1 месяц — 500 ₽\n🔹 3 месяца — 1200 ₽\n🔹 6 месяцев — 2000 ₽\n🔹 1 год — 3500 ₽\n\n💳 Оплата: USDT (криптовалюта)",
        reply_markup=buy_menu()
    )
    await callback.answer()

@dp.callback_query(lambda c: c.data.startswith("pay_"))
async def payment_callback(callback: types.CallbackQuery):
    user_id = callback.from_user.id
    days = int(callback.data.split("_")[1])
    end_date = db.activate_subscription(user_id, days)
    link = await create_vpn_key(user_id)
    if link:
        await callback.message.edit_text(
            f"✅ Подписка активирована!\n📅 Действует до: {end_date.strftime('%d.%m.%Y')}\n\n🔗 Твоя ссылка:\n`{link}`\n\n📱 Импортируй в клиент V2RayNG или Nekoray",
            parse_mode="Markdown",
            reply_markup=main_menu()
        )
    else:
        await callback.message.edit_text("❌ Ошибка. Напишите @admin")
    await callback.answer()

@dp.callback_query(lambda c: c.data == "status")
async def status_callback(callback: types.CallbackQuery):
    user_id = callback.from_user.id
    is_active, msg = db.check_subscription(user_id)
    user = db.get_user(user_id)
    trial_used = "✅" if user and user[3] == 1 else "❌"
    status_text = f"📊 Твой статус:\n\n"
    if is_active:
        status_text += f"✅ Подписка: АКТИВНА\n{msg}\n\n"
    else:
        status_text += f"❌ Подписка: НЕАКТИВНА\n{msg}\n\n"
    status_text += f"🎁 Пробный период: {trial_used}"
    await callback.message.edit_text(
        status_text,
        reply_markup=InlineKeyboardMarkup().add(InlineKeyboardButton("◀️ Назад", callback_data="back"))
    )
    await callback.answer()

@dp.callback_query(lambda c: c.data == "back")
async def back_callback(callback: types.CallbackQuery):
    await callback.message.edit_text("Главное меню:", reply_markup=main_menu())
    await callback.answer()

@dp.callback_query(lambda c: c.data == "help")
async def help_callback(callback: types.CallbackQuery):
    help_text = (
        "🆘 Как подключиться:\n\n1️⃣ Скачай клиент:\n   📱 Android: V2RayNG (Play Market)\n   💻 Windows: Nekoray (GitHub)\n   🍎 iOS: Shadowrocket (App Store)\n\n2️⃣ Скопируй ссылку, которую я выдал\n\n3️⃣ В клиенте нажми 'Импорт из буфера обмена'\n\n4️⃣ Нажми 'Подключиться'\n\n❓ Вопросы: @admin"
    )
    await callback.message.edit_text(
        help_text,
        reply_markup=InlineKeyboardMarkup().add(InlineKeyboardButton("◀️ Назад", callback_data="back"))
    )
    await callback.answer()

async def main():
    print("🚀 Бот запущен!")
    await dp.start_polling(bot)

if __name__ == "__main__":
    asyncio.run(main())
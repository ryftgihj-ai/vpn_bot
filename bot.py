import asyncio
import logging
from datetime import datetime
from aiogram import Bot, Dispatcher, types
from aiogram.types import InlineKeyboardMarkup, InlineKeyboardButton
from aiogram.filters import Command
import aiohttp
import json

from config import (
    BOT_TOKEN, ADMIN_ID, XRAY_API, XRAY_API_TOKEN, SERVER_IP,
    PHOTO_START, PHOTO_SUPPORT, PHOTO_TRIAL, PHOTO_BUY,
    HELP_URL, SUPPORT_LINK, PRICES
)
from database import Database

# ===== НАСТРОЙКА ЛОГГИРОВАНИЯ =====
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(levelname)s - %(message)s"
)
logger = logging.getLogger(__name__)

# ===== ИНИЦИАЛИЗАЦИЯ =====
bot = Bot(token=BOT_TOKEN)
dp = Dispatcher()
db = Database()

# ===== ФУНКЦИЯ СОЗДАНИЯ КЛЮЧА =====
async def create_vpn_key(user_id):
    try:
        connector = aiohttp.TCPConnector(ssl=False)
        async with aiohttp.ClientSession(connector=connector) as session:
            headers = {"Authorization": f"Bearer {XRAY_API_TOKEN}"}
            
            logger.info(f"📡 Запрос к X-UI API для user_id={user_id}")
            
            # Получаем список инбаундов
            async with session.get(f"{XRAY_API}/list", headers=headers) as resp:
                logger.info(f"📥 Ответ /list: status={resp.status}")
                if resp.status != 200:
                    logger.error(f"❌ Ошибка /list: {resp.status}")
                    return None
                data = await resp.json()
                logger.info(f"📄 Данные /list: success={data.get('success')}")
                if not data.get('success'):
                    logger.error(f"❌ X-UI вернул ошибку: {data}")
                    return None
                inbounds = data.get('obj', [])
                if not inbounds:
                    logger.error("❌ Нет входящих подключений")
                    return None
                
                inbound_id = inbounds[0].get('id')
                inbound_port = inbounds[0].get('port')
                inbound_protocol = inbounds[0].get('protocol')
                logger.info(f"✅ Используем inbound: id={inbound_id}, port={inbound_port}, protocol={inbound_protocol}")
            
            # Создаём клиента
            client_id = f"user_{user_id}_{int(datetime.now().timestamp())}"
            email = f"user_{user_id}@vpn.com"
            
            # ===== ИСПРАВЛЕННЫЙ ЗАПРОС: ДОБАВЛЕН PROTOCOL =====
            client_data = {
                "id": inbound_id,
                "protocol": inbound_protocol,
                "settings": json.dumps({
                    "clients": [{
                        "id": client_id,
                        "email": email,
                        "limitIp": 2,
                        "totalGB": 0,
                        "expiryTime": 0,
                        "enable": True
                    }]
                })
            }
            
            logger.info(f"📤 Создаём клиента: email={email}, id={client_id}")
            
            async with session.post(f"{XRAY_API}/add", headers=headers, json=client_data) as resp:
                logger.info(f"📥 Ответ /add: status={resp.status}")
                if resp.status != 200:
                    logger.error(f"❌ Ошибка /add: {resp.status}")
                    try:
                        error_body = await resp.text()
                        logger.error(f"📄 Тело ошибки: {error_body}")
                    except:
                        pass
                    return None
                result = await resp.json()
                logger.info(f"📄 Ответ X-UI: {json.dumps(result, indent=2)}")
                
                if not result.get('success'):
                    logger.error(f"❌ X-UI не создал клиента: {result}")
                    return None
            
            # Формируем ссылку
            if inbound_protocol == "vless":
                link = f"vless://{client_id}@{SERVER_IP}:{inbound_port}?security=reality&encryption=none&type=tcp&flow=xtls-rprx-vision&sni=www.microsoft.com#VPN_BOT"
            else:
                link = f"Ссылка для {inbound_protocol} пока не настроена"
            
            db.save_vpn_link(user_id, link)
            logger.info(f"✅ VPN-ссылка создана для user_id={user_id}")
            return link
                
    except Exception as e:
        logger.error(f"❌ Исключение в create_vpn_key: {e}")
        return None

# ===== КЛАВИАТУРЫ =====
def main_menu():
    keyboard = InlineKeyboardMarkup(inline_keyboard=[
        [
            InlineKeyboardButton(text="🎁 Пробный период", callback_data="trial"),
            InlineKeyboardButton(text="💰 Купить VPN", callback_data="buy")
        ],
        [
            InlineKeyboardButton(text="📊 Мой статус", callback_data="status"),
            InlineKeyboardButton(text="🔗 Получить ссылку", callback_data="get_link")
        ],
        [
            InlineKeyboardButton(text="🆘 Помощь", callback_data="help")
        ]
    ])
    return keyboard

def buy_menu():
    keyboard = InlineKeyboardMarkup(inline_keyboard=[
        [
            InlineKeyboardButton(text="📅 1 месяц - 120₽", callback_data="pay_30"),
            InlineKeyboardButton(text="📅 3 месяца - 350₽", callback_data="pay_90")
        ],
        [
            InlineKeyboardButton(text="📅 6 месяцев - 1000₽", callback_data="pay_180"),
            InlineKeyboardButton(text="📅 1 год - 2000₽", callback_data="pay_365")
        ],
        [
            InlineKeyboardButton(text="◀️ Назад", callback_data="back")
        ]
    ])
    return keyboard

# ===== КОМАНДЫ =====
@dp.message(Command("start"))
async def start_command(message: types.Message):
    user_id = message.from_user.id
    username = message.from_user.username or "NoUsername"
    db.add_user(user_id, username)
    
    await message.answer_photo(
        photo=PHOTO_START,
        caption="👋 Привет! Я бот для выдачи VPN.\nВыбери действие:",
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

# ===== ОБРАБОТЧИКИ CALLBACK =====
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
        await callback.message.answer_photo(
            photo=PHOTO_TRIAL,
            caption=f"✅ Пробный период на 3 дня активирован!\n\n🔗 Твоя ссылка:\n`{link}`\n\n📱 Скачай клиент:\n• Android: https://play.google.com/store/apps/details?id=com.v2ray.ang\n• iPhone: https://apps.apple.com/app/v2raybox/id6446824604\n• Windows/Mac: https://github.com/MatsuriDayo/nekoray/releases",
            parse_mode="Markdown",
            reply_markup=main_menu()
        )
    else:
        await callback.message.answer(f"❌ Ошибка. Напишите {SUPPORT_LINK}")
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
            await callback.message.answer(f"❌ Ошибка. Напишите {SUPPORT_LINK}")
            await callback.answer()
            return
    
    await callback.message.answer(f"✅ Твоя ссылка активна!\n\n🔗 `{link}`\n\n📊 {msg}", parse_mode="Markdown", reply_markup=main_menu())
    await callback.answer()

@dp.callback_query(lambda c: c.data == "buy")
async def buy_callback(callback: types.CallbackQuery):
    await callback.message.delete()
    await callback.message.answer_photo(
        photo=PHOTO_BUY,
        caption="💳 Выбери тариф:",
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
        await callback.message.delete()
        await callback.message.answer(
            f"✅ Подписка активирована!\n📅 Действует до: {end_date.strftime('%d.%m.%Y')}\n\n🔗 Твоя ссылка:\n`{link}`\n\n📱 Импортируй в клиент",
            parse_mode="Markdown",
            reply_markup=main_menu()
        )
    else:
        await callback.message.answer(f"❌ Ошибка. Напишите {SUPPORT_LINK}")
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
    
    await callback.message.delete()
    await callback.message.answer(
        status_text,
        reply_markup=InlineKeyboardMarkup(inline_keyboard=[
            [InlineKeyboardButton(text="◀️ Назад", callback_data="back")]
        ])
    )
    await callback.answer()

@dp.callback_query(lambda c: c.data == "help")
async def help_callback(callback: types.CallbackQuery):
    keyboard = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="📄 Открыть инструкцию", url=HELP_URL)],
        [InlineKeyboardButton(text="📞 Написать поддержке", url=SUPPORT_LINK)]
    ])
    await callback.message.delete()
    await callback.message.answer_photo(
        photo=PHOTO_SUPPORT,
        caption="📖 Инструкция и поддержка:",
        reply_markup=keyboard
    )
    await callback.answer()

@dp.callback_query(lambda c: c.data == "back")
async def back_callback(callback: types.CallbackQuery):
    await callback.message.delete()
    await callback.message.answer(
        "Главное меню:",
        reply_markup=main_menu()
    )
    await callback.answer()

async def main():
    logger.info("🚀 Бот запущен!")
    await dp.start_polling(bot)

if __name__ == "__main__":
    asyncio.run(main())

import asyncio
import logging
from datetime import datetime
from aiogram import Bot, Dispatcher, types
from aiogram.types import InlineKeyboardMarkup, InlineKeyboardButton
from aiogram.filters import Command
import aiohttp
import json
import uuid

from config import (
    BOT_TOKEN, ADMIN_ID, XRAY_API, XRAY_API_TOKEN, SERVER_IP,
    PHOTO_START, PHOTO_SUPPORT, PHOTO_TRIAL, PHOTO_BUY,
    HELP_URL, SUPPORT_LINK, PRICES, CHANNEL_ID, CHANNEL_LINK,
    TARGET_INBOUND_ID
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

# ===== БАЗОВЫЙ URL БЕЗ /panel/api/inbounds =====
BASE_URL = XRAY_API.replace("/panel/api/inbounds", "")

# ===== ФУНКЦИЯ ПРОВЕРКИ ПОДПИСКИ =====
async def check_subscription(user_id):
    try:
        member = await bot.get_chat_member(CHANNEL_ID, user_id)
        return member.status in ['member', 'administrator', 'creator']
    except Exception as e:
        logger.error(f"Ошибка проверки подписки: {e}")
        return False

# ===== ФУНКЦИЯ СОЗДАНИЯ КЛЮЧА =====
async def create_vpn_key(user_id):
    try:
        connector = aiohttp.TCPConnector(ssl=False)
        async with aiohttp.ClientSession(connector=connector) as session:
            headers = {"Authorization": f"Bearer {XRAY_API_TOKEN}"}
            
            logger.info(f"📡 Запрос к X-UI API для user_id={user_id}")
            
            # Получаем список инбаундов
            async with session.get(f"{XRAY_API}/list", headers=headers) as resp:
                if resp.status != 200:
                    logger.error(f"❌ Ошибка /list: {resp.status}")
                    return None
                data = await resp.json()
                if not data.get('success'):
                    logger.error(f"❌ X-UI вернул ошибку: {data}")
                    return None
                inbounds = data.get('obj', [])
                if not inbounds:
                    logger.error("❌ Нет входящих подключений")
                    return None
                
                inbound = next((x for x in inbounds if x.get('id') == TARGET_INBOUND_ID), None)
                
                if not inbound:
                    logger.error(f"❌ Инбаунд с ID={TARGET_INBOUND_ID} не найден!")
                    return None
                
                inbound_id = inbound.get('id')
                logger.info(f"✅ Используем inbound: id={inbound_id}")
            
            # ===== СОЗДАЁМ КЛИЕНТА =====
            email = f"user_{user_id}_{int(datetime.now().timestamp())}@vpn.com"
            
            client_data = {
                "client": {
                    "email": email,
                    "totalGB": 0,
                    "expiryTime": 0,
                    "limitIp": 2,
                    "enable": True
                },
                "inboundIds": [inbound_id]
            }
            
            logger.info(f"📤 Создаём клиента: email={email}")
            
            add_url = f"{BASE_URL}/panel/api/clients/add"
            
            async with session.post(add_url, headers=headers, json=client_data) as resp:
                logger.info(f"📥 Ответ /clients/add: status={resp.status}")
                if resp.status != 200:
                    error_text = await resp.text()
                    logger.error(f"❌ Ошибка /clients/add: {resp.status} — {error_text}")
                    return None
                result = await resp.json()
                logger.info(f"📄 Ответ X-UI: {json.dumps(result, indent=2)}")
                
                if not result.get('success'):
                    logger.error(f"❌ X-UI не создал клиента: {result}")
                    return None
            
            # ===== ПОЛУЧАЕМ ГОТОВУЮ ССЫЛКУ ОТ X-UI =====
            links_url = f"{BASE_URL}/panel/api/clients/links/{email}"
            logger.info(f"🔗 Запрашиваем ссылку: {links_url}")
            
            async with session.get(links_url, headers=headers) as resp:
                logger.info(f"📥 Ответ /clients/links: status={resp.status}")
                if resp.status == 200:
                    links_data = await resp.json()
                    logger.info(f"📄 Ссылки: {json.dumps(links_data, indent=2)}")
                    
                    if links_data.get('success'):
                        links = links_data.get('obj', [])
                        if links and len(links) > 0:
                            link = links[0]
                            logger.info(f"✅ Получена готовая ссылка от X-UI: {link}")
                            db.save_vpn_link(user_id, link)
                            return link
                
                # Если не удалось — формируем вручную
                logger.warning("⚠️ Не удалось получить ссылку от X-UI, формируем вручную")
                
                # Пробуем получить UUID
                get_url = f"{BASE_URL}/panel/api/clients/get/{email}"
                async with session.get(get_url, headers=headers) as resp2:
                    if resp2.status == 200:
                        client_info = await resp2.json()
                        logger.info(f"📄 Инфо о клиенте: {json.dumps(client_info, indent=2)}")
                        obj = client_info.get('obj', {})
                        client_uuid = obj.get('uuid') or obj.get('id') or str(uuid.uuid4())
                    else:
                        client_uuid = str(uuid.uuid4())
                
                link = f"vless://{client_uuid}@{SERVER_IP}:443?encryption=none&security=none&type=tcp#{email}"
                db.save_vpn_link(user_id, link)
                return link
                
    except Exception as e:
        logger.error(f"❌ Исключение: {e}")
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
    
    is_subscribed = await check_subscription(user_id)
    if not is_subscribed:
        keyboard = InlineKeyboardMarkup(inline_keyboard=[
            [InlineKeyboardButton(text="📢 Подписаться на канал", url=CHANNEL_LINK)],
            [InlineKeyboardButton(text="✅ Проверить подписку", callback_data="check_sub")]
        ])
        await message.answer(
            "📢 Для использования бота необходимо подписаться на наш канал!\n\n"
            "Подпишись и нажми 'Проверить подписку'.",
            reply_markup=keyboard
        )
        return
    
    db.add_user(user_id, username)
    await message.answer(
        "👋 Привет! Я бот для выдачи VPN.\nВыбери действие:",
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
@dp.callback_query(lambda c: c.data == "check_sub")
async def check_sub_callback(callback: types.CallbackQuery):
    user_id = callback.from_user.id
    is_subscribed = await check_subscription(user_id)
    
    if is_subscribed:
        username = callback.from_user.username or "NoUsername"
        db.add_user(user_id, username)
        try:
            await callback.message.delete()
        except:
            pass
        await callback.message.answer(
            "✅ Спасибо за подписку!\n\n👋 Привет! Я бот для выдачи VPN.\nВыбери действие:",
            reply_markup=main_menu()
        )
    else:
        await callback.answer("❌ Вы ещё не подписаны на канал!", show_alert=True)
    await callback.answer()

@dp.callback_query(lambda c: c.data == "trial")
async def trial_callback(callback: types.CallbackQuery):
    user_id = callback.from_user.id
    
    is_subscribed = await check_subscription(user_id)
    if not is_subscribed:
        await callback.answer("❌ Подпишитесь на канал!", show_alert=True)
        return
    
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
            f"✅ Пробный период на 3 дня активирован!\n\n🔗 Твоя ссылка:\n`{link}`\n\n📱 Скачай клиент:\n• Android: https://play.google.com/store/apps/details?id=com.v2ray.ang\n• iPhone: https://apps.apple.com/app/v2raybox/id6446824604\n• Windows/Mac: https://github.com/MatsuriDayo/nekoray/releases",
            parse_mode="Markdown",
            reply_markup=main_menu()
        )
    else:
        await callback.message.answer(f"❌ Ошибка. Напишите {SUPPORT_LINK}")
    await callback.answer()

@dp.callback_query(lambda c: c.data == "get_link")
async def get_link_callback(callback: types.CallbackQuery):
    user_id = callback.from_user.id
    
    is_subscribed = await check_subscription(user_id)
    if not is_subscribed:
        await callback.answer("❌ Подпишитесь на канал!", show_alert=True)
        return
    
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
    user_id = callback.from_user.id
    
    is_subscribed = await check_subscription(user_id)
    if not is_subscribed:
        await callback.answer("❌ Подпишитесь на канал!", show_alert=True)
        return
    
    try:
        await callback.message.delete()
    except:
        pass
    await callback.message.answer(
        "💳 Выбери тариф:",
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
        try:
            await callback.message.delete()
        except:
            pass
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
    
    try:
        await callback.message.delete()
    except:
        pass
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
    try:
        await callback.message.delete()
    except:
        pass
    await callback.message.answer(
        "📖 Инструкция и поддержка:",
        reply_markup=keyboard
    )
    await callback.answer()

@dp.callback_query(lambda c: c.data == "back")
async def back_callback(callback: types.CallbackQuery):
    try:
        await callback.message.delete()
    except:
        pass
    await callback.message.answer(
        "Главное меню:",
        reply_markup=main_menu()
    )
    await callback.answer()

# ===== ЗАПУСК С SINGLETON-ЗАЩИТОЙ =====
async def main():
    logger.info("🚀 Бот запущен!")
    
    try:
        await bot.delete_webhook(drop_pending_updates=True)
        logger.info("✅ Вебхук удалён, старые обновления сброшены")
    except Exception as e:
        logger.error(f"Ошибка удаления вебхука: {e}")
    
    await asyncio.sleep(3)
    logger.info("⏳ Начинаем polling...")
    
    await dp.start_polling(bot, skip_updates=True)

if __name__ == "__main__":
    asyncio.run(main())

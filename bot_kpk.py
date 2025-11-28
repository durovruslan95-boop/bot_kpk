import logging
import asyncio
import json
import time
from uuid import uuid4
from pathlib import Path
from aiogram import Bot, Dispatcher, types
from aiogram.types import (
    InlineKeyboardButton,
    InlineKeyboardMarkup,
    ReplyKeyboardMarkup,
    KeyboardButton,
)
from aiogram.filters import Command
import os

logging.basicConfig(level=logging.INFO)

TOKEN = os.getenv("BOT_TOKEN", "8203041313:AAHYrVq9-M6r3lklZzM1LIV41JB57Mn6nf0")
ADMIN_CHAT_ID = int(os.getenv("ADMIN_CHAT_ID", "-1003418331213"))
CHANNEL_ID = int(os.getenv("CHANNEL_ID", "-1003313194527"))

bot = Bot(token=TOKEN)
dp = Dispatcher()

DATA_DIR = Path("./data")
DATA_DIR.mkdir(exist_ok=True)

def save_json(filename, data):
    with open(DATA_DIR / filename, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)

def load_json(filename):
    try:
        with open(DATA_DIR / filename, "r", encoding="utf-8") as f:
            return json.load(f)
    except FileNotFoundError:
        return {}

PENDING_MESSAGES = load_json("pending_messages.json")
PENDING_SUPPORT = load_json("pending_support.json")
MOD_REPLY_PENDING = load_json("mod_reply_pending.json")
USER_ACTIONS = load_json("user_actions.json")
BLOCKED_USERS = load_json("blocked_users.json")
LAST_CONFESSION_TIME = load_json("last_confession_time.json")

CONFESSION_COOLDOWN = 30 * 60  # 30 хвилин

def save_all():
    save_json("pending_messages.json", PENDING_MESSAGES)
    save_json("pending_support.json", PENDING_SUPPORT)
    save_json("mod_reply_pending.json", MOD_REPLY_PENDING)
    save_json("user_actions.json", USER_ACTIONS)
    save_json("blocked_users.json", BLOCKED_USERS)
    save_json("last_confession_time.json", LAST_CONFESSION_TIME)

def is_user_blocked(user_id: int) -> tuple[bool, str]:
    block_info = BLOCKED_USERS.get(str(user_id))
    if not block_info:
        return False, ""
    if block_info.get("until") == "permanent":
        return True, block_info.get("reason", "Заблоковано назавжди")
    until = block_info.get("until")
    if time.time() < until:
        return True, block_info.get("reason", "Тимчасово заблоковано")
    del BLOCKED_USERS[str(user_id)]
    save_all()
    return False, ""

def can_send_confession(user_id: int) -> tuple[bool, int]:
    user_id_str = str(user_id)
    last_time = LAST_CONFESSION_TIME.get(user_id_str, 0)
    current_time = time.time()
    if current_time - last_time >= CONFESSION_COOLDOWN:
        return True, 0
    wait_seconds = CONFESSION_COOLDOWN - (current_time - last_time)
    return False, int(wait_seconds / 60)

main_kb = ReplyKeyboardMarkup(
    keyboard=[
        [KeyboardButton(text="Відправити зізнання")],
        [KeyboardButton(text="Техпідтримка")],
        [KeyboardButton(text="Скасувати")],
    ],
    resize_keyboard=True,
)

@dp.message(Command("start"))
async def cmd_start(message: types.Message):
    if message.chat.type != "private":
        return
    blocked, reason = is_user_blocked(message.from_user.id)
    if blocked:
        await message.answer(f"❌ Ви заблоковані: {reason}")
        return
    await message.answer(
        "Привіт! Обери потрібну дію у меню нижче або надішли свій текст 👇\n\n"
        "⏰ Зізнання: 1 раз на 30 хвилин",
        reply_markup=main_kb,
    )

@dp.message(lambda m: m.chat.type == "private" and m.text == "Відправити зізнання")
async def menu_write_confession(message: types.Message):
    blocked, reason = is_user_blocked(message.from_user.id)
    if blocked:
        await message.answer(f"❌ Ви заблоковані: {reason}")
        return
    can_send, wait_min = can_send_confession(message.from_user.id)
    if not can_send:
        await message.answer(
            f"⏳ Зачекайте ще {wait_min} хв перед наступним зізнанням.\n"
            f"Ліміт: 1 зізнання кожні 30 хвилин.",
            reply_markup=main_kb,
        )
        return
    USER_ACTIONS[str(message.from_user.id)] = "confession"
    save_all()
    await message.answer(
        "✍️ Введи своє зізнання у відповідь на це повідомлення.",
        reply_markup=main_kb,
    )

@dp.message(lambda m: m.chat.type == "private" and m.text == "Техпідтримка")
async def menu_support(message: types.Message):
    blocked, reason = is_user_blocked(message.from_user.id)
    if blocked:
        await message.answer(f"❌ Ви заблоковані: {reason}")
        return
    USER_ACTIONS[str(message.from_user.id)] = "support"
    save_all()
    await message.answer(
        "Опишіть вашу проблему чи питання у відповідь на це повідомлення.",
        reply_markup=main_kb,
    )

@dp.message(lambda m: m.chat.type == "private" and m.text == "Скасувати")
async def menu_cancel(message: types.Message):
    USER_ACTIONS[str(message.from_user.id)] = None
    save_all()
    await message.answer(
        "Введення скасовано. Головне меню нижче 👇",
        reply_markup=main_kb,
    )

@dp.message(lambda m: m.chat.type == "private")
async def handle_user_message(message: types.Message):
    blocked, reason = is_user_blocked(message.from_user.id)
    if blocked:
        await message.answer(f"❌ Ви заблоковані: {reason}")
        return
    if message.text in ["Відправити зізнання", "Техпідтримка", "Скасувати"]:
        return

    user_id = message.from_user.id
    user_id_str = str(user_id)
    action = USER_ACTIONS.get(user_id_str)

    if action == "confession":
        can_send, wait_min = can_send_confession(user_id)
        if not can_send:
            await message.answer(
                f"⏳ Зачекайте ще {wait_min} хв перед наступним зізнанням.\n"
                f"Ліміт: 1 зізнання кожні 30 хвилин.",
                reply_markup=main_kb,
            )
            return
        conf_id = str(uuid4())
        PENDING_MESSAGES[conf_id] = {
            "text": message.text,
            "user_id": user_id,
        }
        LAST_CONFESSION_TIME[user_id_str] = time.time()
        save_all()
        kb = InlineKeyboardMarkup(
            inline_keyboard=[
                [
                    InlineKeyboardButton(
                        text="✅ Одобрити", callback_data=f"approve:{conf_id}"
                    ),
                    InlineKeyboardButton(
                        text="❌ Відхилити", callback_data=f"reject:{conf_id}"
                    ),
                ],
                [
                    InlineKeyboardButton(
                        text="🔨 Блок 1 год", callback_data=f"block:{conf_id}:3600"
                    ),
                    InlineKeyboardButton(
                        text="🔨 Блок 24 год", callback_data=f"block:{conf_id}:86400"
                    ),
                ],
                [
                    InlineKeyboardButton(
                        text="🔨 Блок назавжди",
                        callback_data=f"block:{conf_id}:permanent",
                    )
                ],
            ]
        )
        await bot.send_message(
            ADMIN_CHAT_ID,
            f"💌 Нове анонімне зізнання:\n\n{message.text}\n\n"
            f"🕐 Останнє: {time.strftime('%H:%M', time.localtime(LAST_CONFESSION_TIME[user_id_str]))}",
            reply_markup=kb,
        )
        await message.answer(
            "Дякуємо! Твоє повідомлення надіслано на модерацію 💌\n"
            "⏰ Наступне можна буде надіслати через 30 хвилин.",
            reply_markup=main_kb,
        )

    elif action == "support":
        conf_id = str(uuid4())
        PENDING_SUPPORT[conf_id] = {
            "text": message.text,
            "user_id": user_id,
        }
        save_all()
        kb = InlineKeyboardMarkup(
            inline_keyboard=[
                [
                    InlineKeyboardButton(
                        text="💬 Відповісти", callback_data=f"support_reply:{conf_id}"
                    ),
                    InlineKeyboardButton(
                        text="❌ Відхилити",
                        callback_data=f"support_reject:{conf_id}",
                    ),
                ],
                [
                    InlineKeyboardButton(
                        text="🔨 Блок 1 год", callback_data=f"block:{conf_id}:3600"
                    ),
                    InlineKeyboardButton(
                        text="🔨 Блок 24 год", callback_data=f"block:{conf_id}:86400"
                    ),
                ],
                [
                    InlineKeyboardButton(
                        text="🔨 Блок назавжди",
                        callback_data=f"block:{conf_id}:permanent",
                    )
                ],
            ]
        )
        await bot.send_message(
            ADMIN_CHAT_ID,
            f"📞 Запит у техпідтримку:\n\n{message.text}",
            reply_markup=kb,
        )
        await message.answer(
            "Ваше звернення до техпідтримки надіслано.", reply_markup=main_kb
        )

    USER_ACTIONS[user_id_str] = None
    save_all()

@dp.callback_query(lambda c: c.data and c.data.startswith(("approve:", "reject:")))
async def process_confessions(call: types.CallbackQuery):
    action, conf_id = call.data.split(":", 1)
    data = PENDING_MESSAGES.get(conf_id)
    if not data:
        await call.answer("Це повідомлення більше недоступне.", show_alert=True)
        return
    text = data["text"]
    user_id = data["user_id"]
    if action == "approve":
        await bot.send_message(
            CHANNEL_ID, f"💌 Анонімне зізнання:\n\n{text}\n\n@ziznannya_kpk"
        )
        try:
            await bot.send_message(user_id, "Ваше зізнання опубліковано в каналі ✅")
        except Exception:
            pass
        await call.answer("✅ Опубліковано")
    else:
        try:
            await bot.send_message(user_id, "Ваше зізнання відхилено ❌")
        except Exception:
            pass
        await call.answer("❌ Відхилено")
    PENDING_MESSAGES.pop(conf_id, None)
    save_all()
    await call.message.edit_reply_markup(None)

@dp.callback_query(
    lambda c: c.data and c.data.startswith(("support_reply:", "support_reject:"))
)
async def process_support(call: types.CallbackQuery):
    action, conf_id = call.data.split(":", 1)
    data = PENDING_SUPPORT.get(conf_id)
    if not data:
        await call.answer("Це повідомлення більше недоступне.", show_alert=True)
        return
    if action == "support_reply":
        await call.message.answer(
            "💬 Введіть відповідь для клієнта у наступному повідомленні.\n"
            f"Відповідайте саме на це повідомлення (ID: {call.message.message_id})"
        )
        MOD_REPLY_PENDING[str(call.message.message_id)] = {
            "conf_id": conf_id,
            "user_id": data["user_id"],
        }
        save_all()
        await call.answer()
    else:
        try:
            await bot.send_message(
                data["user_id"], "Ваше звернення техпідтримки відхилено ❌"
            )
        except Exception:
            pass
        await call.answer("❌ Відхилено")
        PENDING_SUPPORT.pop(conf_id, None)
        save_all()
    await call.message.edit_reply_markup(None)

@dp.callback_query(lambda c: c.data and c.data.startswith("block:"))
async def handle_block(call: types.CallbackQuery):
    parts = call.data.split(":")
    conf_id, duration = parts[1], parts[2]
    data = PENDING_MESSAGES.get(conf_id) or PENDING_SUPPORT.get(conf_id)
    if not data:
        await call.answer("Користувач не знайдений.", show_alert=True)
        return
    user_id = data["user_id"]
    reason = f"Блокування модератором ({call.from_user.full_name or call.from_user.username})"
    if duration == "permanent":
        BLOCKED_USERS[str(user_id)] = {"until": "permanent", "reason": reason}
        block_msg = "🔨 Заблоковано НАЗАВЖДИ"
    else:
        until = time.time() + int(duration)
        BLOCKED_USERS[str(user_id)] = {"until": until, "reason": reason}
        block_msg = f"🔨 Заблоковано на {int(duration)//3600} год"
    save_all()
    try:
        await bot.send_message(
            user_id,
            f"❌ Ви {block_msg.lower()}!\nПричина: {reason}\n\n"
            "За деталями зверніться до адміністрації.",
        )
    except Exception:
        pass
    await call.answer(block_msg)
    await call.message.edit_reply_markup(None)

@dp.message(lambda m: m.chat.id == ADMIN_CHAT_ID and m.chat.type in ("group", "supergroup"))
async def moderator_reply(message: types.Message):
    if not message.reply_to_message:
        await message.reply(
            "Будь ласка, відповідайте на повідомлення бота з техпідтримкою."
        )
        return
    parent_id = str(message.reply_to_message.message_id)
    key_id = None
    if parent_id in MOD_REPLY_PENDING:
        key_id = parent_id
    elif str(int(parent_id) - 1) in MOD_REPLY_PENDING:
        key_id = str(int(parent_id) - 1)
    if not key_id:
        await message.reply(
            "Це повідомлення не містить відкритого звернення техпідтримки."
        )
        return
    info = MOD_REPLY_PENDING.pop(key_id)
    save_all()
    user_id = info["user_id"]
    try:
        await bot.send_message(
            user_id, f"💬 Відповідь техпідтримки:\n\n{message.text}"
        )
        await message.reply("✅ Відповідь надіслано користувачу")
        PENDING_SUPPORT.pop(info["conf_id"], None)
        save_all()
    except Exception as e:
        logging.error(f"Помилка при надсиланні відповіді: {e}")
        await message.reply(f"❌ Помилка: {e}")

async def periodic_post():
    while True:
        try:
            await bot.send_message(
                CHANNEL_ID,
                "💌 Хочеш розповісти, хто тобі подобається, але соромишся?\n\n"
                "Тут ти можеш надіслати повністю анонімне зізнання про хлопця чи дівчину з будь-якої групи нашого коледжу.\n\n"
                "👉 Пиши свої історії, симпатії, флірт, краші — ми опублікуємо ❤️\n"
                "⏰ Ліміт: 1 зізнання кожні 30 хвилин\n\n"
                "@ziznannya_kpk_bot",
            )
        except Exception:
            pass
        await asyncio.sleep(3600)

async def main():
    asyncio.create_task(periodic_post())
    while True:
        try:
            await dp.start_polling(bot, skip_updates=True)
        except Exception as e:
            logging.error(f"Polling error: {e}")
            await asyncio.sleep(60)

if __name__ == "__main__":
    asyncio.run(main())

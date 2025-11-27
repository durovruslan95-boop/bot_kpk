import logging
import asyncio
import json
from uuid import uuid4
from pathlib import Path

from aiogram import Bot, Dispatcher, types
from aiogram.types import (
    InlineKeyboardButton,
    InlineKeyboardMarkup,
    ReplyKeyboardMarkup,
    KeyboardButton,
)
from aiogram.filters import Command  # фільтр команд

logging.basicConfig(level=logging.INFO)

TOKEN = "8203041313:AAHYrVq9-M6r3lklZzM1LIV41JB57Mn6nf0"
ADMIN_CHAT_ID = -1003418331213   # ID групи модераторів
CHANNEL_ID = -1003313194527      # ID каналу

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


def save_all():
    save_json("pending_messages.json", PENDING_MESSAGES)
    save_json("pending_support.json", PENDING_SUPPORT)
    save_json("mod_reply_pending.json", MOD_REPLY_PENDING)
    save_json("user_actions.json", USER_ACTIONS)


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
    await message.answer(
        "Привіт! Обери потрібну дію у меню нижче або надішли свій текст 👇",
        reply_markup=main_kb,
    )


@dp.message(lambda m: m.chat.type == "private" and m.text == "Відправити зізнання")
async def menu_write_confession(message: types.Message):
    USER_ACTIONS[str(message.from_user.id)] = "confession"
    save_all()
    await message.answer(
        "Введи своє зізнання у відповідь на це повідомлення.",
        reply_markup=main_kb,
    )


@dp.message(lambda m: m.chat.type == "private" and m.text == "Техпідтримка")
async def menu_support(message: types.Message):
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
    if message.text in ["Відправити зізнання", "Техпідтримка", "Скасувати"]:
        return

    user_id_str = str(message.from_user.id)
    action = USER_ACTIONS.get(user_id_str, "confession")
    conf_id = str(uuid4())

    if action == "support":
        PENDING_SUPPORT[conf_id] = {
            "text": message.text,
            "user_id": message.from_user.id,
        }
        save_all()

        kb = InlineKeyboardMarkup(
            inline_keyboard=[
                [
                    InlineKeyboardButton(
                        text="Відповісти", callback_data=f"support_reply:{conf_id}"
                    ),
                    InlineKeyboardButton(
                        text="Відхилити", callback_data=f"support_reject:{conf_id}"
                    ),
                ]
            ]
        )

        await bot.send_message(
            ADMIN_CHAT_ID,
            f"Запит у техпідтримку:\n\n{message.text}",
            reply_markup=kb,
        )
        await message.answer(
            "Ваше звернення до техпідтримки надіслано.",
            reply_markup=main_kb,
        )
        USER_ACTIONS[user_id_str] = None
        save_all()
    else:
        PENDING_MESSAGES[conf_id] = {
            "text": message.text,
            "user_id": message.from_user.id,
        }
        save_all()

        kb = InlineKeyboardMarkup(
            inline_keyboard=[
                [
                    InlineKeyboardButton(
                        text="Одобрити", callback_data=f"approve:{conf_id}"
                    ),
                    InlineKeyboardButton(
                        text="Відхилити", callback_data=f"reject:{conf_id}"
                    ),
                ]
            ]
        )

        await bot.send_message(
            ADMIN_CHAT_ID,
            f"Нове анонімне повідомлення:\n\n{message.text}",
            reply_markup=kb,
        )
        await message.answer(
            "Дякуємо! Твоє повідомлення надіслано на модерацію 💌",
            reply_markup=main_kb,
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
            CHANNEL_ID,
            f"💌 Анонімне зізнання:\n\n{text}\n\n@ziznannya_kpk",
        )
        await bot.send_message(
            user_id, "Ваше зізнання опубліковано в каналі ✅"
        )
        await call.answer("Опубліковано ✔️")
    else:
        await bot.send_message(
            user_id, "Ваше зізнання відхилено ❌"
        )
        await call.answer("Відхилено ❌")

    PENDING_MESSAGES.pop(conf_id, None)
    save_all()


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
            f"Введіть відповідь для клієнта у наступному повідомленні.\n"
            f"Відповідайте саме на це повідомлення (ID: {call.message.message_id})"
        )
        MOD_REPLY_PENDING[str(call.message.message_id)] = {
            "conf_id": conf_id,
            "user_id": data["user_id"],
        }
        save_all()
        await call.answer()
    else:
        await bot.send_message(
            data["user_id"],
            "Ваше звернення техпідтримки відхилено ❌",
        )
        await call.answer("Відхилено ❌")
        PENDING_SUPPORT.pop(conf_id, None)
        save_all()


@dp.message(lambda m: m.chat.id == ADMIN_CHAT_ID and m.chat.type in ("group", "supergroup"))
async def moderator_reply(message: types.Message):
    logging.info(
        f"DEBUG MODERATOR REPLY: chat.id={message.chat.id}, "
        f"reply_to_message_id={getattr(message.reply_to_message, 'message_id', None)}, "
        f"MOD_REPLY_PENDING keys={list(MOD_REPLY_PENDING.keys())}"
    )

    if not message.reply_to_message:
        await message.reply(
            "Будь ласка, відповідайте на повідомлення бота з техпідтримкою."
        )
        return

    parent_id = str(message.reply_to_message.message_id)

    if parent_id in MOD_REPLY_PENDING:
        key_id = parent_id
    elif str(int(parent_id) - 1) in MOD_REPLY_PENDING:
        key_id = str(int(parent_id) - 1)
    else:
        logging.warning(
            f"Reply message id {parent_id} not found in MOD_REPLY_PENDING"
        )
        await message.reply(
            "Це повідомлення не містить відкритого звернення техпідтримки."
        )
        return

    info = MOD_REPLY_PENDING.pop(key_id)
    save_all()

    user_id = info["user_id"]

    try:
        await bot.send_message(
            user_id, f"Відповідь техпідтримки:\n\n{message.text}"
        )
        await message.reply("Відповідь надіслано користувачу ✅")
        PENDING_SUPPORT.pop(info["conf_id"], None)
        save_all()
    except Exception as e:
        logging.error(f"Помилка при надсиланні відповіді: {e}")
        await message.reply(f"Помилка при надсиланні відповіді: {e}")


async def periodic_post():
    while True:
        await bot.send_message(
            CHANNEL_ID,
            "Хочеш розповісти, хто тобі подобається, але соромишся?\n"
            "Тут ти можеш надіслати повністю анонімне зізнання про хлопця чи дівчину з будь-якої групи нашого коледжу.\n"
            "Пиши свої історії, симпатії, флірт, краші — ми опублікуємо ❤️👇\n"
            "@ziznannya_kpk_bot",
        )
        await asyncio.sleep(3600)


async def main():
    asyncio.create_task(periodic_post())
    await dp.start_polling(bot, skip_updates=True)


if __name__ == "__main__":
    asyncio.run(main())

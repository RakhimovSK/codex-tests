"""Telegram bot implementing the specified user flow using urllib and SQLite."""

import os
import time
import json
import sqlite3
import urllib.parse
import urllib.request
from datetime import datetime, timedelta

TOKEN = os.getenv("BOT_TOKEN")  # Telegram bot token
ADMIN_CHAT_ID = os.getenv("ADMIN_CHAT_ID")  # Chat ID for admin notifications
REQUIRED_CHANNEL_ID = os.getenv("REQUIRED_CHANNEL_ID")  # Channel for subscription check

DB_PATH = "bot.db"
FIRST_GUIDE_PATH = "first_guide.pdf"
PAID_GUIDE_PATH = "paid_guide.pdf"

# Steps in the conversation
STEP_START = "start"
STEP_WAIT_SUB = "wait_sub"
STEP_SURVEY_NAME = "survey_name"
STEP_SURVEY_CLASS = "survey_class"
STEP_SURVEY_SUBJECTS = "survey_subjects"
STEP_SURVEY_CONTACT = "survey_contact"
STEP_SURVEY_PHONE = "survey_phone"
STEP_DONE = "done"

def init_db():
    conn = sqlite3.connect(DB_PATH)
    cur = conn.cursor()
    cur.execute(
        """
        CREATE TABLE IF NOT EXISTS users (
            user_id INTEGER PRIMARY KEY,
            step TEXT,
            registered_at TEXT,
            subscribed INTEGER,
            got_first_guide INTEGER,
            next_free_guide_at TEXT,
            name TEXT,
            grade TEXT,
            subjects TEXT,
            contact TEXT,
            phone TEXT,
            paid INTEGER
        )
        """
    )
    conn.commit()
    conn.close()

def db_get_user(user_id):
    conn = sqlite3.connect(DB_PATH)
    cur = conn.cursor()
    cur.execute("SELECT * FROM users WHERE user_id=?", (user_id,))
    row = cur.fetchone()
    conn.close()
    return row

def db_add_user(user_id):
    conn = sqlite3.connect(DB_PATH)
    cur = conn.cursor()
    cur.execute(
        """
        INSERT OR IGNORE INTO users (
            user_id, step, registered_at, subscribed, got_first_guide,
            next_free_guide_at, paid
        ) VALUES (?, ?, ?, 0, 0, '', 0)
        """,
        (user_id, STEP_WAIT_SUB, datetime.utcnow().isoformat()),
    )
    conn.commit()
    conn.close()

def db_update(user_id, **fields):
    conn = sqlite3.connect(DB_PATH)
    cur = conn.cursor()
    keys = ", ".join(f"{k}=?" for k in fields.keys())
    values = list(fields.values()) + [user_id]
    cur.execute(f"UPDATE users SET {keys} WHERE user_id=?", values)
    conn.commit()
    conn.close()

def tg_request(method, params=None, files=None):
    if params is None:
        params = {}
    url = f"https://api.telegram.org/bot{TOKEN}/{method}"
    if files:
        boundary = "----WebKitFormBoundary7MA4YWxkTrZu0gW"
        data = []
        for k, v in params.items():
            data.append(f"--{boundary}")
            data.append(f'Content-Disposition: form-data; name="{k}"')
            data.append("")
            data.append(str(v))
        for k, (filename, content) in files.items():
            data.append(f"--{boundary}")
            data.append(f'Content-Disposition: form-data; name="{k}"; filename="{filename}"')
            data.append("Content-Type: application/octet-stream")
            data.append("")
            data.append(content)
        data.append(f"--{boundary}--")
        body = "\r\n".join(data).encode()
        request = urllib.request.Request(url, data=body)
        request.add_header("Content-Type", f"multipart/form-data; boundary={boundary}")
    else:
        request = urllib.request.Request(url, data=urllib.parse.urlencode(params).encode())
    with urllib.request.urlopen(request) as resp:
        return json.loads(resp.read().decode())

def send_message(chat_id, text, reply_markup=None):
    params = {"chat_id": chat_id, "text": text}
    if reply_markup:
        params["reply_markup"] = json.dumps(reply_markup)
    tg_request("sendMessage", params)

def send_document(chat_id, file_path, caption=None):
    with open(file_path, "rb") as f:
        content = f.read()
    files = {"document": (os.path.basename(file_path), content)}
    params = {"chat_id": chat_id}
    if caption:
        params["caption"] = caption
    tg_request("sendDocument", params, files=files)

def get_updates(offset=None):
    params = {"timeout": 10}
    if offset:
        params["offset"] = offset
    data = tg_request("getUpdates", params)
    return data.get("result", [])

def check_subscription(user_id):
    if not REQUIRED_CHANNEL_ID:
        return True
    params = {"chat_id": REQUIRED_CHANNEL_ID, "user_id": user_id}
    data = tg_request("getChatMember", params)
    status = data.get("result", {}).get("status")
    return status in ("member", "creator", "administrator")

def handle_start(user_id, chat_id):
    user = db_get_user(user_id)
    if user:
        step = user[1]
    else:
        db_add_user(user_id)
        step = STEP_WAIT_SUB
    if step == STEP_WAIT_SUB:
        ask_subscription(chat_id)
    elif step == STEP_SURVEY_NAME:
        send_message(chat_id, "Как вас зовут?")
    elif step == STEP_SURVEY_CLASS:
        send_message(chat_id, "В каком вы классе?")
    elif step == STEP_SURVEY_SUBJECTS:
        send_message(chat_id, "Какие предметы интересуют?")
    elif step == STEP_SURVEY_CONTACT:
        send_message(chat_id, "Telegram или WhatsApp?")
    elif step == STEP_SURVEY_PHONE:
        send_message(chat_id, "Нажмите кнопку, чтобы отправить телефон", {
            "keyboard": [[{"text": "Отправить телефон", "request_contact": True}]],
            "one_time_keyboard": True,
            "resize_keyboard": True
        })
    else:
        send_message(chat_id, "/start повторно")

def ask_subscription(chat_id):
    kb = {"inline_keyboard": [[{"text": "Я подписался", "callback_data": "check_sub"}]]}
    send_message(chat_id, "Пожалуйста, подпишитесь на канал и нажмите кнопку", kb)

def send_first_guide(chat_id, user_id):
    send_document(chat_id, FIRST_GUIDE_PATH)
    db_update(user_id, got_first_guide=1)
    time.sleep(5)
    send_message(chat_id, "Хотите индивидуальное предложение и скидки? Ответьте на несколько вопросов")
    send_message(chat_id, "Как вас зовут?")
    db_update(user_id, step=STEP_SURVEY_NAME)

def process_survey(user_id, chat_id, text, contact=None):
    user = db_get_user(user_id)
    step = user[1]
    if step == STEP_SURVEY_NAME:
        db_update(user_id, name=text, step=STEP_SURVEY_CLASS)
        send_message(chat_id, "В каком вы классе?")
    elif step == STEP_SURVEY_CLASS:
        db_update(user_id, grade=text, step=STEP_SURVEY_SUBJECTS)
        send_message(chat_id, "Какие предметы интересуют?")
    elif step == STEP_SURVEY_SUBJECTS:
        db_update(user_id, subjects=text, step=STEP_SURVEY_CONTACT)
        send_message(chat_id, "Telegram или WhatsApp?")
    elif step == STEP_SURVEY_CONTACT:
        db_update(user_id, contact=text, step=STEP_SURVEY_PHONE)
        send_message(chat_id, "Нажмите кнопку, чтобы отправить телефон", {
            "keyboard": [[{"text": "Отправить телефон", "request_contact": True}]],
            "one_time_keyboard": True,
            "resize_keyboard": True
        })
    elif step == STEP_SURVEY_PHONE and contact:
        db_update(user_id, phone=contact, step=STEP_DONE)
        finalize_survey(user_id, chat_id)

def finalize_survey(user_id, chat_id):
    user = db_get_user(user_id)
    summary = (
        f"User {user_id}\n"
        f"Имя: {user[6]}\n"
        f"Класс: {user[7]}\n"
        f"Предметы: {user[8]}\n"
        f"Контакт: {user[9]}\n"
        f"Телефон: {user[10]}"
    )
    if ADMIN_CHAT_ID:
        send_message(ADMIN_CHAT_ID, summary)
    send_message(chat_id, "Спасибо! Вот список платных гайдов. Нажмите кнопку, чтобы получить сейчас", {
        "inline_keyboard": [[{"text": "Получить сейчас", "callback_data": "buy"}]]
    })

def handle_payment(user_id, chat_id):
    send_message(chat_id, "Этот гайд стоит 500 руб 99 рублей. Оплата пока не реализована.")
    db_update(user_id, paid=1)
    send_document(chat_id, PAID_GUIDE_PATH)
    next_time = datetime.utcnow() + timedelta(hours=72)
    db_update(user_id, next_free_guide_at=next_time.isoformat())

def main():
    init_db()
    last_update = None
    while True:
        updates = get_updates(last_update)
        for upd in updates:
            last_update = upd["update_id"] + 1
            if "message" in upd:
                msg = upd["message"]
                user_id = msg["from"]["id"]
                chat_id = msg["chat"]["id"]
                if msg.get("text") == "/start":
                    handle_start(user_id, chat_id)
                elif msg.get("contact"):
                    process_survey(user_id, chat_id, "", msg["contact"]["phone_number"])
                elif msg.get("text"):
                    process_survey(user_id, chat_id, msg.get("text"))
            elif "callback_query" in upd:
                cb = upd["callback_query"]
                user_id = cb["from"]["id"]
                chat_id = cb["message"]["chat"]["id"]
                data = cb["data"]
                if data == "check_sub":
                    if check_subscription(user_id):
                        send_first_guide(chat_id, user_id)
                    else:
                        send_message(chat_id, "Подписка не обнаружена. Попробуйте ещё раз")
                elif data == "buy":
                    handle_payment(user_id, chat_id)
        time.sleep(1)

if __name__ == "__main__":
    main()

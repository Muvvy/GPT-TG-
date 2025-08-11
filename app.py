import os
import psycopg2
from flask import Flask, request, jsonify
from flask_cors import CORS
import telebot
import g4f

TOKEN = os.getenv("TELEGRAM_TOKEN")
WEBHOOK_URL_BASE = os.getenv("WEBHOOK_URL_BASE")  # Например: https://your-service.onrender.com
WEBHOOK_URL_PATH = f"/{TOKEN}/"
DATABASE_URL = os.getenv("DATABASE_URL")  # PostgreSQL URL для Render

if not TOKEN:
    raise ValueError("Не найден TELEGRAM_TOKEN в переменных окружения")
if not WEBHOOK_URL_BASE:
    raise ValueError("Не найден WEBHOOK_URL_BASE в переменных окружения")
if not DATABASE_URL:
    raise ValueError("Не найден DATABASE_URL в переменных окружения")

bot = telebot.TeleBot(TOKEN)
app = Flask(__name__)
CORS(app)  # Разрешаем запросы с GitHub Pages

MAX_HISTORY_LENGTH = 20
DEFAULT_MODEL = "gpt-4"

# --- Работа с PostgreSQL ---
def get_db_conn():
    return psycopg2.connect(DATABASE_URL, sslmode='require')

def init_db():
    with get_db_conn() as conn:
        with conn.cursor() as cur:
            cur.execute("""
                CREATE TABLE IF NOT EXISTS history (
                    chat_id BIGINT,
                    role TEXT,
                    content TEXT,
                    timestamp TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                );
            """)
            conn.commit()

def get_history(chat_id):
    with get_db_conn() as conn:
        with conn.cursor() as cur:
            cur.execute("""
                SELECT role, content FROM history
                WHERE chat_id = %s
                ORDER BY timestamp ASC
                LIMIT %s
            """, (chat_id, MAX_HISTORY_LENGTH))
            rows = cur.fetchall()
    return [{"role": row[0], "content": row[1]} for row in rows]

def append_history(chat_id, role, content):
    with get_db_conn() as conn:
        with conn.cursor() as cur:
            cur.execute("""
                INSERT INTO history (chat_id, role, content)
                VALUES (%s, %s, %s)
            """, (chat_id, role, content))
            conn.commit()

def reset_history(chat_id):
    with get_db_conn() as conn:
        with conn.cursor() as cur:
            cur.execute("DELETE FROM history WHERE chat_id = %s", (chat_id,))
            conn.commit()

def get_stats(chat_id):
    with get_db_conn() as conn:
        with conn.cursor() as cur:
            cur.execute("SELECT COUNT(*) FROM history WHERE chat_id = %s", (chat_id,))
            count = cur.fetchone()[0]
    return count

init_db()

# --- Telegram команды ---
@bot.message_handler(commands=['start'])
def start(message):
    chat_id = message.chat.id
    reset_history(chat_id)
    bot.send_message(chat_id, "Привет! Я бот на базе GPT-4.\n"
                              "Команды: /help /reset /info /price /stats")

@bot.message_handler(commands=['help'])
def help_cmd(message):
    chat_id = message.chat.id
    bot.send_message(chat_id,
        "/start - начать диалог\n"
        "/help - список команд\n"
        "/reset - сбросить историю\n"
        "/info - о боте\n"
        "/price - цена\n"
        "/stats - статистика")

@bot.message_handler(commands=['reset'])
def reset(message):
    reset_history(message.chat.id)
    bot.send_message(message.chat.id, "История сброшена.")

@bot.message_handler(commands=['info'])
def info(message):
    bot.send_message(message.chat.id,
        "Я бот на базе GPT. Запоминаю историю. Бесплатный.\n"
        "Автор: @seregannj")

@bot.message_handler(commands=['price'])
def price_cmd(message):
    bot.send_message(message.chat.id, "!!!FREE - БЕСПЛАТНО!!!")

@bot.message_handler(commands=['stats'])
def stats(message):
    bot.send_message(message.chat.id,
        f"Всего сообщений: {get_stats(message.chat.id)}")

# --- Обработка сообщений Telegram ---
@bot.message_handler(func=lambda message: True)
def handle_message(message):
    chat_id = message.chat.id
    text = message.text
    append_history(chat_id, "user", text)
    bot.send_chat_action(chat_id, 'typing')
    try:
        response = g4f.ChatCompletion.create(
            model=DEFAULT_MODEL,
            messages=get_history(chat_id)
        )
    except Exception as e:
        print(f"Ошибка: {e}")
        response = "Ошибка обработки запроса."
    append_history(chat_id, "assistant", response)
    bot.send_message(chat_id, response)

# --- API для GitHub Pages ---
@app.route("/chat", methods=["POST"])
def chat_api():
    data = request.json
    user_message = data.get("message")
    chat_id = data.get("chat_id", 1)  # Если нет Telegram, можно фиксированный ID
    append_history(chat_id, "user", user_message)
    try:
        response = g4f.ChatCompletion.create(
            model=DEFAULT_MODEL,
            messages=get_history(chat_id)
        )
    except Exception as e:
        print(f"Ошибка API: {e}")
        response = "Ошибка обработки запроса."
    append_history(chat_id, "assistant", response)
    return jsonify({"response": response})

# --- Webhook для Telegram ---
@app.route(WEBHOOK_URL_PATH, methods=['POST'])
def webhook():
    update = telebot.types.Update.de_json(request.get_data().decode('utf-8'))
    bot.process_new_updates([update])
    return '', 200

if __name__ == "__main__":
    bot.remove_webhook()
    bot.set_webhook(url=WEBHOOK_URL_BASE + WEBHOOK_URL_PATH)

import os
import psycopg2
from flask import Flask, request
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

# --- Команды бота ---

@bot.message_handler(commands=['start'])
def start(message):
    chat_id = message.chat.id
    reset_history(chat_id)
    bot.send_message(chat_id, "Привет! Я бот на базе GPT-4. Просто напиши мне что-нибудь и я тебе отвечу.\n"
                              "Также советую посмотреть все комманды: /help")

@bot.message_handler(commands=['help'])
def help_cmd(message):
    chat_id = message.chat.id
    help_text = (
        "Доступные команды:\n"
        "/start - начать диалог\n"
        "/help - показать список команд\n"
        "/reset - сбросить историю\n"
        "/info - информация о боте\n"
        "/price - Цена (бесплатно)\n"
        "/stats - статистика сообщений"
    )
    bot.send_message(chat_id, help_text)

@bot.message_handler(commands=['reset'])
def reset(message):
    chat_id = message.chat.id
    reset_history(chat_id)
    bot.send_message(chat_id, "История диалога была успешно сброшена.")

@bot.message_handler(commands=['info'])
def info(message):
    chat_id = message.chat.id
    info_text = (
        "Я бот на базе GPT.\n"
        "Могу поддерживать диалог и запоминать историю сообщений.\n"
        "Я абсолютно бесплатный. Иногда могу ошибаться (всё-таки я же ИИ).\n"
        "Если ты хочешь поддержать этот проект, или хочешь предложить идею, обращайся к моему хозяину: @seregannj!"
    )
    bot.send_message(chat_id, info_text)

@bot.message_handler(commands=['price'])
def price_cmd(message):
    chat_id = message.chat.id
    price_text = "!!!FREE - БЕСПЛАТНО!!!"
    bot.send_message(chat_id, price_text)

@bot.message_handler(commands=['stats'])
def stats(message):
    chat_id = message.chat.id
    count = get_stats(chat_id)
    bot.send_message(chat_id, f"Всего сообщений в истории: {count}")

# --- Обработка сообщений с индикатором "печатает" ---

@bot.message_handler(func=lambda message: True)
def handle_message(message):
    chat_id = message.chat.id
    text = message.text

    append_history(chat_id, "user", text)
    bot.send_chat_action(chat_id, 'typing')  # Показываем "печатает"

    try:
        response = g4f.ChatCompletion.create(
            model=DEFAULT_MODEL,
            messages=get_history(chat_id)
        )
    except Exception as e:
        print(f"Ошибка при вызове g4f: {e}")
        response = "Извините, произошла ошибка при обработке вашего запроса."

    append_history(chat_id, "assistant", response)
    bot.send_message(chat_id, response)

# --- Webhook endpoint ---

@app.route(WEBHOOK_URL_PATH, methods=['POST'])
def webhook():
    json_string = request.get_data().decode('utf-8')
    update = telebot.types.Update.de_json(json_string)
    bot.process_new_updates([update])
    return '', 200

if __name__ == "__main__":
    bot.remove_webhook()
    bot.set_webhook(url=WEBHOOK_URL_BASE + WEBHOOK_URL_PATH)
    port = int(os.environ.get('PORT', 5000))
    app.run(host="0.0.0.0", port=port)

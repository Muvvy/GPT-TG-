import os
import psycopg2
from flask import Flask, request, jsonify
import telebot
import g4f

TOKEN = os.getenv("TELEGRAM_TOKEN")
WEBHOOK_URL_BASE = os.getenv("WEBHOOK_URL_BASE")
WEBHOOK_URL_PATH = f"/{TOKEN}/"
DATABASE_URL = os.getenv("DATABASE_URL")

if not TOKEN:
    raise ValueError("Не найден TELEGRAM_TOKEN")
if not WEBHOOK_URL_BASE:
    raise ValueError("Не найден WEBHOOK_URL_BASE")
if not DATABASE_URL:
    raise ValueError("Не найден DATABASE_URL")

bot = telebot.TeleBot(TOKEN)
app = Flask(__name__)

MAX_HISTORY_LENGTH = 20
DEFAULT_MODEL = "gpt-4"

# --- PostgreSQL ---
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

# --- Добавляем CORS вручную ---
@app.after_request
def add_cors_headers(response):
    response.headers["Access-Control-Allow-Origin"] = "https://muvvy.github.io"
    response.headers["Access-Control-Allow-Methods"] = "GET, POST, OPTIONS"
    response.headers["Access-Control-Allow-Headers"] = "Content-Type"
    return response

# --- API для GitHub Pages ---
@app.route("/chat", methods=["POST", "OPTIONS"])
def chat():
    if request.method == "OPTIONS":
        return '', 200

    data = request.get_json()
    chat_id = data.get("chat_id", 0)
    message = data.get("message", "")

    append_history(chat_id, "user", message)

    try:
        response = g4f.ChatCompletion.create(
            model="gpt-4",
            messages=get_history(chat_id)
        )
    except Exception as e:
        print(f"Ошибка g4f: {e}")
        response = "Ошибка при обработке запроса."

    append_history(chat_id, "assistant", response)
    return jsonify({"response": response})

# --- Webhook для Telegram ---
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

import os
import psycopg2
from flask import Flask, request, jsonify, render_template
import telebot
import g4f

# ========== Конфиг ==========
TOKEN = os.getenv("TELEGRAM_TOKEN")
WEBHOOK_URL_BASE = os.getenv("WEBHOOK_URL_BASE")  # например https://your-service.onrender.com
WEBHOOK_URL_PATH = f"/{TOKEN}/" if TOKEN else None

# Если не задано через env, будет использоваться URL, который ты ранее указал.
DATABASE_URL = os.getenv(
    "DATABASE_URL",
    "postgresql://gpt_ai_db_user:K7xIvBXQqK0zzx0P4kkBG7amH2zviyD5@dpg-d2ceo7vdiees73fjvkp0-a/gpt_ai_db"
)

MAX_HISTORY_LENGTH = int(os.getenv("MAX_HISTORY_LENGTH", 20))
DEFAULT_MODEL = os.getenv("DEFAULT_MODEL", "gpt-4")

if not TOKEN:
    raise ValueError("Не найден TELEGRAM_TOKEN в переменных окружения")
if not WEBHOOK_URL_BASE:
    raise ValueError("Не найден WEBHOOK_URL_BASE в переменных окружения")
if not DATABASE_URL:
    raise ValueError("Не найден DATABASE_URL в переменных окружения (или fallback тоже пуст)")

# ========== Init ==========
bot = telebot.TeleBot(TOKEN)
app = Flask(__name__, template_folder="templates", static_folder="static")

# ========== DB helpers ==========
def get_db_conn():
    # Для Render/Managed PG используем sslmode=require
    return psycopg2.connect(DATABASE_URL, sslmode='require')

def init_db():
    with get_db_conn() as conn:
        with conn.cursor() as cur:
            cur.execute("""
                CREATE TABLE IF NOT EXISTS history (
                    id SERIAL PRIMARY KEY,
                    chat_id TEXT,
                    role TEXT,
                    content TEXT,
                    timestamp TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                );
            """)
            conn.commit()

def get_history(chat_id):
    """
    Возвращает последние MAX_HISTORY_LENGTH сообщений в виде списка {'role':..., 'content':...'}
    в хронологическом порядке (от старых к новым).
    """
    with get_db_conn() as conn:
        with conn.cursor() as cur:
            cur.execute("""
                SELECT role, content FROM history
                WHERE chat_id = %s
                ORDER BY timestamp DESC
                LIMIT %s
            """, (str(chat_id), MAX_HISTORY_LENGTH))
            rows = cur.fetchall()
    # rows сейчас в порядке newest->oldest, переворачиваем
    rows.reverse()
    return [{"role": row[0], "content": row[1]} for row in rows]

def append_history(chat_id, role, content):
    with get_db_conn() as conn:
        with conn.cursor() as cur:
            cur.execute("""
                INSERT INTO history (chat_id, role, content)
                VALUES (%s, %s, %s)
            """, (str(chat_id), role, content))
            conn.commit()

def reset_history(chat_id):
    with get_db_conn() as conn:
        with conn.cursor() as cur:
            cur.execute("DELETE FROM history WHERE chat_id = %s", (str(chat_id),))
            conn.commit()

def get_stats(chat_id):
    with get_db_conn() as conn:
        with conn.cursor() as cur:
            cur.execute("SELECT COUNT(*) FROM history WHERE chat_id = %s", (str(chat_id),))
            count = cur.fetchone()[0]
    return count

init_db()

# ========== Telegram bot handlers ==========
@bot.message_handler(commands=['start'])
def start(message):
    reset_history(message.chat.id)
    bot.send_message(message.chat.id, "Привет! Я бот на базе GPT. Напиши что-нибудь — отвечу.\nСписок команд: /help")

@bot.message_handler(commands=['help'])
def help_cmd(message):
    help_text = (
        "/start — начать\n"
        "/help — помощь\n"
        "/reset — сбросить историю\n"
        "/info — информация\n"
        "/price — цена\n"
        "/stats — статистика сообщений"
    )
    bot.send_message(message.chat.id, help_text)

@bot.message_handler(commands=['reset'])
def reset_cmd(message):
    reset_history(message.chat.id)
    bot.send_message(message.chat.id, "История успешно сброшена.")

@bot.message_handler(commands=['info'])
def info_cmd(message):
    info_text = (
        "Я GPT-бот. Сохраняю историю диалога в PostgreSQL.\n"
        "Могу ошибаться — используй критически :)"
    )
    bot.send_message(message.chat.id, info_text)

@bot.message_handler(commands=['price'])
def price_cmd(message):
    bot.send_message(message.chat.id, "💸 FREE — бесплатно")

@bot.message_handler(commands=['stats'])
def stats_cmd(message):
    cnt = get_stats(message.chat.id)
    bot.send_message(message.chat.id, f"Всего записей истории: {cnt}")

@bot.message_handler(func=lambda m: True)
def handle_message(message):
    chat_id = message.chat.id
    text = message.text or ""
    append_history(chat_id, "user", text)
    try:
        bot.send_chat_action(chat_id, 'typing')
    except Exception:
        pass

    try:
        history = get_history(chat_id)
        # g4f API: используем messages формат
        response = g4f.ChatCompletion.create(
            model=DEFAULT_MODEL,
            messages=history
        )
    except Exception as e:
        response = f"Ошибка при вызове модели: {e}"

    append_history(chat_id, "assistant", response)
    bot.send_message(chat_id, response)

# ========== Web App (frontend) ==========
@app.route("/")
def index():
    return render_template("index.html")

@app.route("/api/chat", methods=["POST"])
def web_chat():
    data = request.get_json(force=True)
    user_msg = data.get("message", "").strip()
    if not user_msg:
        return jsonify({"error": "Пустое сообщение"}), 400

    # Используем chat_id "webapp" (можешь изменить на уникальный per-user если захочешь)
    chat_id = "webapp"
    append_history(chat_id, "user", user_msg)

    try:
        history = get_history(chat_id)
        response = g4f.ChatCompletion.create(
            model=DEFAULT_MODEL,
            messages=history
        )
    except Exception as e:
        return jsonify({"error": f"Ошибка при вызове модели: {e}"}), 500

    append_history(chat_id, "assistant", response)
    return jsonify({"response": response})

# ========== Webhook endpoint (Telegram -> Flask) ==========
@app.route(WEBHOOK_URL_PATH, methods=['POST'])
def webhook():
    # Telebot expects a JSON update
    json_string = request.get_data().decode('utf-8')
    update = telebot.types.Update.de_json(json_string)
    bot.process_new_updates([update])
    return '', 200

# ========== Запуск ========== 
if __name__ == "__main__":
    # при старте удаляем старый webhook и ставим новый
    bot.remove_webhook()
    bot.set_webhook(url=WEBHOOK_URL_BASE + WEBHOOK_URL_PATH)
    port = int(os.environ.get('PORT', 5000))
    app.run(host="0.0.0.0", port=port)

import os
import psycopg2
import telebot
import g4f

TOKEN = os.getenv("TELEGRAM_TOKEN")
DATABASE_URL = os.getenv("DATABASE_URL")

if not TOKEN or not DATABASE_URL:
    raise ValueError("Отсутствуют необходимые переменные окружения: TELEGRAM_TOKEN или DATABASE_URL")

bot = telebot.TeleBot(TOKEN)

MAX_HISTORY_LENGTH = 20
DEFAULT_MODEL = "gpt-4"

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

@bot.message_handler(commands=['start'])
def start(message):
    chat_id = message.chat.id
    reset_history(chat_id)
    bot.send_message(chat_id, "Привет! Я бот на базе GPT-4. Просто напиши мне что-нибудь и я тебе отвечу.\n"
                              "Также советую посмотреть все команды: /help")

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
        "Если хочешь поддержать проект или предложить идею, пиши @seregannj!"
    )
    bot.send_message(chat_id, info_text)

@bot.message_handler(commands=['price'])
def price_cmd(message):
    chat_id = message.chat.id
    bot.send_message(chat_id, "!!!FREE - БЕСПЛАТНО!!!")

@bot.message_handler(commands=['stats'])
def stats(message):
    chat_id = message.chat.id
    count = get_stats(chat_id)
    bot.send_message(chat_id, f"Всего сообщений в истории: {count}")

@bot.message_handler(func=lambda message: True)
def handle_message(message):
    chat_id = message.chat.id
    text = message.text
    print(f"Получено сообщение от {chat_id}: {text}")  # Для отладки

    append_history(chat_id, "user", text)
    bot.send_chat_action(chat_id, 'typing')

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

if __name__ == "__main__":
    print("Бот запущен в режиме polling!")
    bot.remove_webhook()
    bot.polling(none_stop=True)

import os
from flask import Flask, request
import telebot
import g4f

TOKEN = os.getenv("TELEGRAM_TOKEN")
if not TOKEN:
    raise ValueError("Не найден TELEGRAM_TOKEN в переменных окружения")

WEBHOOK_URL_BASE = os.getenv("WEBHOOK_URL_BASE")  # Например: https://your-service.onrender.com
if not WEBHOOK_URL_BASE:
    raise ValueError("Не найден WEBHOOK_URL_BASE в переменных окружения")

WEBHOOK_URL_PATH = f"/{TOKEN}/"

bot = telebot.TeleBot(TOKEN)
app = Flask(__name__)

MAX_HISTORY_LENGTH = 20
user_histories = {}

def get_history(chat_id):
    return user_histories.get(chat_id, [])

def append_history(chat_id, role, content):
    history = user_histories.get(chat_id, [])
    history.append({"role": role, "content": content})
    if len(history) > MAX_HISTORY_LENGTH:
        history = history[-MAX_HISTORY_LENGTH:]
    user_histories[chat_id] = history

@bot.message_handler(commands=['start'])
def start(message):
    chat_id = message.chat.id
    user_histories[chat_id] = []
    bot.send_message(chat_id, "Привет! Я бот на базе GPT-4 через g4f. Просто напиши мне что-нибудь.")

@bot.message_handler(commands=['help'])
def help_cmd(message):
    chat_id = message.chat.id
    help_text = (
        "Доступные команды:\n"
        "/start - начать диалог\n"
        "/help - показать список команд\n"
        "/reset - сбросить историю\n"
        "/info - информация о боте"
    )
    bot.send_message(chat_id, help_text)

@bot.message_handler(commands=['reset'])
def reset(message):
    chat_id = message.chat.id
    user_histories[chat_id] = []
    bot.send_message(chat_id, "История диалога была успешно сброшена.")

@bot.message_handler(commands=['info'])
def info(message):
    chat_id = message.chat.id
    info_text = (
        "Я бот на базе GPT-4 через библиотеку g4f.\n"
        "Могу поддерживать диалог и запоминать историю сообщений."
    )
    bot.send_message(chat_id, info_text)

@bot.message_handler(func=lambda message: True)
def handle_message(message):
    chat_id = message.chat.id
    text = message.text

    append_history(chat_id, "user", text)

    try:
        response = g4f.ChatCompletion.create(
            model="gpt-4",
            messages=get_history(chat_id)
        )
    except Exception as e:
        print(f"Ошибка при вызове g4f: {e}")
        response = "Извините, произошла ошибка при обработке вашего запроса."

    append_history(chat_id, "assistant", response)
    bot.send_message(chat_id, response)

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

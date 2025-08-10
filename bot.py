import os
from flask import Flask, request
import telebot

TOKEN = os.getenv("TELEGRAM_TOKEN")
if not TOKEN:
    raise ValueError("Не найден TELEGRAM_TOKEN в переменных окружения")

bot = telebot.TeleBot(TOKEN)
app = Flask(__name__)

WEBHOOK_URL_BASE = os.getenv("WEBHOOK_URL_BASE")  # публичный URL Render с https
WEBHOOK_URL_PATH = f"/{TOKEN}/"

# Обработчик команды /start
@bot.message_handler(commands=['start'])
def start(message):
    bot.send_message(message.chat.id, "Привет! Я бот на webhook.")

# Обработка входящих обновлений от Telegram
@app.route(WEBHOOK_URL_PATH, methods=['POST'])
def webhook():
    json_string = request.get_data().decode('utf-8')
    update = telebot.types.Update.de_json(json_string)
    bot.process_new_updates([update])
    return '', 200

if __name__ == "__main__":
    # Устанавливаем webhook у Telegram
    bot.remove_webhook()
    bot.set_webhook(url=WEBHOOK_URL_BASE + WEBHOOK_URL_PATH)

    # Запускаем Flask сервер на порту Render
    port = int(os.environ.get('PORT', 5000))
    app.run(host="0.0.0.0", port=port)

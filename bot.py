import os
import telebot

# Получаем токен из переменных окружения
TOKEN = os.getenv("TELEGRAM_TOKEN")
if not TOKEN:
    raise ValueError("Не найден TELEGRAM_TOKEN в переменных окружения")

bot = telebot.TeleBot(TOKEN)

# История сообщений в памяти (ограничим 20 сообщениями)
MAX_HISTORY_LENGTH = 20
user_histories = {}

import g4f

def get_history(chat_id):
    return user_histories.get(chat_id, [])

def append_history(chat_id, role, content):
    history = user_histories.get(chat_id, [])
    history.append({"role": role, "content": content})
    if len(history) > MAX_HISTORY_LENGTH:
        history = history[-MAX_HISTORY_LENGTH:]
    user_histories[chat_id] = history

# Команды
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

# Обработка текстовых сообщений
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

if __name__ == "__main__":
    print("Бот запущен...")
    bot.infinity_polling()

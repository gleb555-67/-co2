import telebot
import sqlite3
from datetime import datetime
from telebot import apihelper

# ---------- НАСТРОЙКА ПРОКСИ (если Telegram заблокирован) ----------
apihelper.proxy = {'https': 'socks5://127.0.0.1:9050'}

# --------------------- ТОКЕН БОТА -----------------------------
BOT_TOKEN = "8494854564:AAHkTILO_fEVDVYDhTOhwP2XoChc1O6nIiE"

bot = telebot.TeleBot(BOT_TOKEN)
user_data = {}  # временное хранилище данных во время диалога

# ------------------ КОЭФФИЦИЕНТЫ CO2 --------------------------
K_ELEC = 0.4   # кг CO₂ на 1 кВт·ч
K_CAR  = 0.15  # кг CO₂ на 1 км пробега
K_WASTE = 0.5  # кг CO₂ на 1 кг мусора

# ---------------------- БАЗА ДАННЫХ SQLITE ----------------------
def init_db():
    """Создаёт таблицу calculations, если её ещё нет."""
    conn = sqlite3.connect('co2.db')
    cur = conn.cursor()
    cur.execute('''
        CREATE TABLE IF NOT EXISTS calculations (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            chat_id INTEGER NOT NULL,
            date TEXT NOT NULL,
            elec_month REAL,
            car_month REAL,
            waste_month REAL,
            total_year REAL
        )
    ''')
    conn.commit()
    conn.close()

def save_calculation(chat_id, elec, car, waste, total_year):
    """Сохраняет один расчёт в базу данных."""
    conn = sqlite3.connect('co2.db')
    cur = conn.cursor()
    cur.execute('''
        INSERT INTO calculations (chat_id, date, elec_month, car_month, waste_month, total_year)
        VALUES (?, ?, ?, ?, ?, ?)
    ''', (chat_id, datetime.now().isoformat(), elec, car, waste, total_year))
    conn.commit()
    conn.close()

# Инициализируем БД при запуске
init_db()

# ------------------- ОБРАБОТЧИК КОМАНД -------------------------
@bot.message_handler(commands=['start'])
def start(msg):
    user_data[msg.chat.id] = {}
    bot.send_message(msg.chat.id,
        "🌱 Привет! Я помогу оценить твой углеродный след.\n\n"
        "💡 Сколько примерно **кВт·ч** электроэнергии вы расходуете в месяц?\n"
        "(Просто отправьте число или фото счётчика — я пока принимаю только числа 😊)"
    )
    bot.register_next_step_handler(msg, step_elec)

@bot.message_handler(commands=['cancel'])
def cancel(msg):
    """Отменяет текущий диалог и очищает состояние."""
    if msg.chat.id in user_data:
        del user_data[msg.chat.id]
    bot.clear_step_handler_by_chat_id(chat_id=msg.chat.id)
    bot.send_message(msg.chat.id, "❌ Диалог отменён. Чтобы начать заново, введите /start.")

# ------------------- ШАГИ ДИАЛОГА -----------------------------
def step_elec(msg):
    """Обработка ввода электричества."""
    # Проверка на команду /cancel внутри диалога
    if msg.text and msg.text.startswith('/cancel'):
        cancel(msg)
        return

    if msg.content_type == 'photo':
        bot.send_message(msg.chat.id,
            "📸 Спасибо за фото! Но я пока не умею распознавать показания. "
            "Введите, пожалуйста, число:"
        )
        bot.register_next_step_handler(msg, step_elec)
        return
    try:
        val = float(msg.text.strip().replace(',', '.'))
        if val < 0:
            raise ValueError
        user_data[msg.chat.id]['elec'] = val
    except:
        bot.send_message(msg.chat.id, "❌ Нужно положительное число. Попробуйте ещё раз:")
        bot.register_next_step_handler(msg, step_elec)
        return

    bot.send_message(msg.chat.id, "🚗 Сколько километров вы проезжаете на автомобиле в месяц?")
    bot.register_next_step_handler(msg, step_car)

def step_car(msg):
    """Обработка ввода километража."""
    if msg.text and msg.text.startswith('/cancel'):
        cancel(msg)
        return

    try:
        val = float(msg.text.strip().replace(',', '.'))
        if val < 0:
            raise ValueError
        user_data[msg.chat.id]['car'] = val
    except:
        bot.send_message(msg.chat.id, "❌ Введите положительное число километров:")
        bot.register_next_step_handler(msg, step_car)
        return

    bot.send_message(msg.chat.id, "🗑️ А сколько примерно килограммов мусора вы выбрасываете в месяц?")
    bot.register_next_step_handler(msg, step_waste)

def step_waste(msg):
    """Обработка ввода мусора и финальный расчёт."""
    if msg.text and msg.text.startswith('/cancel'):
        cancel(msg)
        return

    try:
        val = float(msg.text.strip().replace(',', '.'))
        if val < 0:
            raise ValueError
        user_data[msg.chat.id]['waste'] = val
    except:
        bot.send_message(msg.chat.id, "❌ Введите положительное число килограммов:")
        bot.register_next_step_handler(msg, step_waste)
        return

    # Расчёт годового следа
    d = user_data[msg.chat.id]
    year_elec = d['elec'] * 12 * K_ELEC
    year_car  = d['car'] * 12 * K_CAR
    year_waste = d['waste'] * 12 * K_WASTE
    total = year_elec + year_car + year_waste

    # Сохраняем результат в БД
    save_calculation(msg.chat.id, d['elec'], d['car'], d['waste'], total)

    # Формируем ответ
    resp = (
        "🌍 **Ваш годовой углеродный след**\n\n"
        f"💡 Электричество: {year_elec:.1f} кг CO₂\n"
        f"🚗 Автомобиль:    {year_car:.1f} кг CO₂\n"
        f"🗑️ Мусор:         {year_waste:.1f} кг CO₂\n"
        f"━━━━━━━━━━━━━━━━━━━━\n"
        f"📊 **ВСЕГО:         {total:.1f} кг CO₂**\n\n"
        "🌱 Полезные советы по снижению: https://www.un.org/ru/actnow/ten-actions"
    )
    bot.send_message(msg.chat.id, resp, parse_mode="Markdown")

    # Очищаем временные данные
    del user_data[msg.chat.id]

# ---------------------- ЗАПУСК БОТА ----------------------------
if __name__ == '__main__':
    print("Бот запущен...")
    bot.infinity_polling()

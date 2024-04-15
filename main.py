import threading
import time
import schedule
import telebot
from database import SessionLocal, init_db
from models import Student, Attendance, Group
from datetime import datetime
from models import User
from telebot.types import InlineKeyboardMarkup, InlineKeyboardButton, ReplyKeyboardRemove
import csv

TOKEN = '7023709428:AAFvL7q7wUOwcxe0m5s-DYYsxx4-RDOwztY'
bot = telebot.TeleBot(TOKEN)

PREFIXES = ["ИС", "ТМ", "П", "ЭВМ", "РЭТ", "КПИиА"]

PING_INTERVAL_SECONDS = 20

auth_users = {}

init_db()  # Инициализация базы данных

def ping_bot():
    while True:
        try:
            bot.send_chat_action(chat_id="2099795903", action="typing")
            print("Bot is alive!")
        except Exception as e:
            print(f"Bot is down! Error: {e}")
            print("Restarting bot...")
            start_bot()
        time.sleep(PING_INTERVAL_SECONDS)

schedule.every(5).minutes.do(ping_bot)

ping_thread = threading.Thread(target=ping_bot)
ping_thread.start()

def start_bot():
    try:
        bot.polling(none_stop=True)
    except Exception as e:
        print(f"Error in polling: {e}")
        print("Restarting bot...")
        start_bot()  # Перезапуск бота при возникновении ошибки

# Бесконечный цикл для выполнения заданий планировщика и перезапуска бота
    while True:
        schedule.run_pending()  # Выполнение запланированных заданий
        start_bot()  # Перезапуск бота, если он упал
        time.sleep(1) # Пауза между итерациями цикла
    
def update_auth_users(user_id, is_auth):
    auth_users[user_id] = is_auth

# Функция для проверки авторизации пользователя
def is_user_auth(user_id):
    return user_id in auth_users and auth_users[user_id]    
    
def export_attendance_data():
    session = SessionLocal()
    filename = f"attendance_data_{datetime.now().strftime('%Y-%m-%d_%H-%M-%S')}.csv"
    try:
        with open(filename, mode='w', newline='', encoding='utf-8') as file:
            writer = csv.writer(file)
            writer.writerow(['Group Name', 'Student Name', 'Status', 'Minutes Late', 'Date'])
            
            attendances = session.query(Attendance).join(Student).join(Group).all()
            for attendance in attendances:
                group_name = attendance.student.group.name
                student_name = f"{attendance.student.first_name} {attendance.student.last_name}"
                writer.writerow([group_name, student_name, attendance.status, attendance.minutes_late, attendance.date.strftime('%Y-%m-%d %H:%M')])
    except Exception as e:
        print(f"Ошибка при экспорте данных: {e}")
        filename = None
    finally:
        session.close()
    return filename

@bot.message_handler(commands=['login'])
def login(message):
    bot.send_message(message.chat.id, "Введите ваш логин:")
    bot.register_next_step_handler(message, process_username_step)

def process_username_step(message):
    username = message.text
    bot.send_message(message.chat.id, "Введите ваш пароль:")
    bot.register_next_step_handler(message, lambda m: process_password_step(m, username))

def process_password_step(message, username):
    password = message.text
    session = SessionLocal()
    user = session.query(User).filter(User.username == username, User.password == password).first()
    session.close()
    if user:
        bot.send_message(message.chat.id, "Вы успешно вошли в систему!")
        update_auth_users(message.from_user.id, True)  # Сохраняем информацию об авторизации пользователя
    else:
        bot.send_message(message.chat.id, "Неверный логин или пароль!")

def create_main_keyboard():
    keyboard = telebot.types.ReplyKeyboardMarkup(row_width=2, resize_keyboard=True)
    keyboard.row("Отметить студента", "Экспорт данных")
    keyboard.row("Войти в систему")
    return keyboard

# Обработчик команды /logout
@bot.message_handler(commands=['logout'])
def logout(message):
    bot.send_message(message.chat.id, "Вы вышли из системы!")
    # Здесь можно сбросить флаг авторизации для пользователя

# Декоратор для проверки авторизации перед выполнением команд
def auth_required(func):
    def wrapper(message):
        if is_user_auth(message.from_user.id):
            func(message)
        else:
            bot.send_message(message.chat.id, "Вы не авторизованы!")
    return wrapper

@bot.message_handler(commands=['start'])
def send_welcome(message):
    bot.reply_to(message, "Привет! Выберите действие:", reply_markup=create_main_keyboard())

@bot.message_handler(func=lambda message: True)
def handle_messages(message):
    if message.text == "Отметить студента":
        choose_prefix(message)
    elif message.text == "Экспорт данных":
        handle_export_command(message)
    elif message.text == "Войти в систему":
        login(message)
    else:
        bot.reply_to(message, "Извините, я не могу понять ваш запрос. Пожалуйста, используйте кнопки на клавиатуре.")

@bot.message_handler(commands=['groups'])
@auth_required
def choose_prefix(message):
    keyboard = telebot.types.ReplyKeyboardMarkup(resize_keyboard=True)
    for prefix in PREFIXES:
        keyboard.add(prefix)
    bot.send_message(message.chat.id, "Выберите отделениие:", reply_markup=keyboard)
    bot.register_next_step_handler(message, list_groups)

def list_groups(message):
    prefix = message.text
    session = SessionLocal()
    try:
        groups = session.query(Group).filter(Group.name.like(f'{prefix}%')).all()
        if groups:
            markup = InlineKeyboardMarkup()
            for group in groups:
                markup.add(InlineKeyboardButton(text=group.name, callback_data=f'group_{group.id}'))
            bot.send_message(message.chat.id, "Выберите группу:", reply_markup=markup)
        else:
            bot.send_message(message.chat.id, f"Нет групп с префиксом '{prefix}'.")
    except Exception as e:
        bot.send_message(message.chat.id, f"Ошибка: {e}")
    finally:
        session.close()

@bot.callback_query_handler(func=lambda call: call.data.startswith('group_'))
def callback_select_group(call):
    group_id = int(call.data.split('_')[1])
    session = SessionLocal()  # Создаем новую сессию
    students = session.query(Student).filter(Student.group_id == group_id).all()
    markup = InlineKeyboardMarkup()
    for student in students:
        markup.add(InlineKeyboardButton(text=f"{student.first_name} {student.last_name}", callback_data=f'student_{student.id}'))
    bot.send_message(call.message.chat.id, "Выберите студента:", reply_markup=markup)
    session.close()  # Не забудьте закрыть сессию

@bot.callback_query_handler(func=lambda call: call.data.startswith('student_'))
def callback_select_student(call):
    student_id = int(call.data.split('_')[1])
    markup = InlineKeyboardMarkup()
    markup.add(InlineKeyboardButton(text="Опоздал", callback_data=f'late_{student_id}'))
    markup.add(InlineKeyboardButton(text="Отсутствует", callback_data=f'absent_{student_id}'))
    bot.send_message(call.message.chat.id, "Выберите статус студента:", reply_markup=markup)

@bot.callback_query_handler(func=lambda call: call.data.startswith('late_'))
def callback_mark_late(call):
    student_id = int(call.data.split('_')[1])
    bot.send_message(call.message.chat.id, "Введите количество минут опоздания:")
    bot.register_next_step_handler(call.message, lambda message: mark_attendance_late(message, student_id))

@bot.callback_query_handler(func=lambda call: call.data.startswith('absent_'))
def callback_mark_absent(call):
    student_id = int(call.data.split('_')[1])
    mark_attendance_absent(call.message, student_id)

def mark_attendance_late(message, student_id):
    try:
        minutes_late = int(message.text)
        session = SessionLocal()
        attendance = Attendance(date=datetime.now(), status="Опоздал", minutes_late=minutes_late, student_id=student_id)
        session.add(attendance)
        session.commit()
        bot.reply_to(message, f"Опоздание на {minutes_late} минут успешно отмечено.")
    except ValueError:
        bot.reply_to(message, "Пожалуйста, введите число. Попробуйте снова.")
    except Exception as e:
        bot.reply_to(message, f"Ошибка: {e}")
    finally:
        session.close()

def mark_attendance_absent(message, student_id):
    try:
        session = SessionLocal()
        attendance = Attendance(date=datetime.now(), status="Отсутствует", minutes_late=0, student_id=student_id)
        session.add(attendance)
        session.commit()
        bot.reply_to(message, "Студент отмечен как отсутствующий.")
    except Exception as e:
        bot.reply_to(message, f"Ошибка: {e}")
    finally:
        session.close()

@bot.message_handler(commands=['cancel'])
def handle_cancel(message):
    bot.reply_to(message, "Текущее действие отменено.")
    bot.send_message(message.chat.id, "Привет! Чтобы отметить студента, начните с выбора группы командой /groups", reply_markup=ReplyKeyboardRemove())

@bot.message_handler(commands=['export'])
def handle_export_command(message):
    chat_id = message.chat.id
    try:
        filename = export_attendance_data()
        if filename:
            with open(filename, 'rb') as file:
                bot.send_document(chat_id, file, caption="Данные посещаемости")
        else:
            bot.send_message(chat_id, "Не удалось экспортировать данные.")
    except Exception as e:
        bot.send_message(chat_id, f"Ошибка при экспорте данных: {e}")

@bot.message_handler(commands=['addgroup'])
def command_add_group(message):
    try:
        group_name = message.text.split(maxsplit=1)[1]  # Получаем имя группы после команды
        session = SessionLocal()
        new_group = Group(name=group_name)
        session.add(new_group)
        session.commit()
        bot.reply_to(message, f"Группа '{group_name}' успешно добавлена с ID {new_group.id}.")
        session.close()
    except IndexError:
        bot.reply_to(message, "Пожалуйста, укажите название группы после команды /addgroup.")
    except Exception as e:
        bot.reply_to(message, f"Ошибка при добавлении группы: {e}")

@bot.message_handler(commands=['addstudents'])
def command_add_students(message):
    bot.send_message(message.chat.id, "Выберите группу для добавления студентов:", reply_markup=create_groups_markup())
    bot.register_next_step_handler(message, add_students)

def create_groups_markup():
    markup = InlineKeyboardMarkup()
    session = SessionLocal()
    groups = session.query(Group).all()
    for group in groups:
        markup.add(InlineKeyboardButton(text=group.name, callback_data=f'addstudent_{group.id}'))
    session.close()
    return markup

def add_students(message):
    group_id = int(message.text.split('_')[1])
    bot.send_message(message.chat.id, "Пожалуйста, отправьте список студентов в формате 'Имя Фамилия', каждый студент на новой строке.")
    bot.register_next_step_handler(message, lambda m: save_students(m, group_id))

def save_students(message, group_id):
    try:
        session = SessionLocal()
        students_list = message.text.split('\n')
        for student_name in students_list:
            first_name, last_name = student_name.strip().split(' ', 1)
            new_student = Student(first_name=first_name, last_name=last_name, group_id=group_id)
            session.add(new_student)
        session.commit()
        bot.reply_to(message, f"Студенты успешно добавлены в группу.")
        session.close()
    except Exception as e:
        bot.reply_to(message, f"Ошибка при добавлении студентов: {e}")

bot.polling()

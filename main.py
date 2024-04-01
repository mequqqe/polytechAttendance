import telebot
from database import SessionLocal, init_db
from models import Student, Attendance, Group
from datetime import datetime
from telebot.types import InlineKeyboardMarkup, InlineKeyboardButton
from enum import Enum
import csv
from datetime import datetime

TOKEN = '7023709428:AAFvL7q7wUOwcxe0m5s-DYYsxx4-RDOwztY'
bot = telebot.TeleBot(TOKEN)

init_db()  # Инициализация базы данных

class BotState(Enum):
    NORMAL = 0
    CHOOSING_GROUP = 1
    CHOOSING_STUDENT = 2
    CHOOSING_ACTION = 3
    WAITING_FOR_MINUTES = 4
    ADDING_STUDENTS = 5

# Словарь для отслеживания состояний пользователей
user_states = {}

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



def set_state(user_id, state, data=None):
    user_states[user_id] = (state, data)

def get_state(user_id):
    return user_states.get(user_id, (BotState.NORMAL, None))

def create_groups_markup(groups):
    markup = InlineKeyboardMarkup()
    for group in groups:
        markup.add(InlineKeyboardButton(text=group.name, callback_data=f'group_{group.id}'))
    return markup

def create_students_markup(students):
    markup = InlineKeyboardMarkup()
    for student in students:
        button_text = f"{student.first_name} {student.last_name}"
        markup.add(InlineKeyboardButton(text=button_text, callback_data=f'student_{student.id}'))
    return markup

def add_group(name):
    session = SessionLocal()
    try:
        new_group = Group(name=name)
        session.add(new_group)
        session.commit()
        return new_group.id  # Возвращаем ID новой группы
    except Exception as e:
        print(f"Ошибка при добавлении группы: {e}")
        return None
    finally:
        session.close()

def add_students_to_group(group_id, students_list):
    session = SessionLocal()
    try:
        for student_name in students_list:
            first_name, last_name = student_name.strip().split(' ', 1)
            new_student = Student(first_name=first_name, last_name=last_name, group_id=group_id)
            session.add(new_student)
        session.commit()
    except Exception as e:
        session.rollback()
        print(f"Ошибка при добавлении студентов: {e}")
    finally:
        session.close()


@bot.message_handler(commands=['start', 'help'])
def send_welcome(message):
    bot.reply_to(message, "Привет! Чтобы отметить студента, начните с выбора группы командой /groups")

@bot.message_handler(commands=['groups'])
def list_groups(message):
    session = SessionLocal()
    try:
        groups = session.query(Group).all()
        markup = create_groups_markup(groups)
        bot.send_message(message.chat.id, "Выберите группу:", reply_markup=markup)
        set_state(message.from_user.id, BotState.CHOOSING_GROUP)
    except Exception as e:
        bot.send_message(message.chat.id, f"Ошибка: {e}")
    finally:
        session.close()

@bot.callback_query_handler(func=lambda call: True)
def handle_callback_query(call):
    state, data = get_state(call.from_user.id)
    session = SessionLocal()

    try:
        if call.data.startswith('group_'):
            group_id = int(call.data.split('_')[1])
            students = session.query(Student).filter(Student.group_id == group_id).all()
            markup = create_students_markup(students)
            bot.edit_message_text("Выберите студента:", chat_id=call.message.chat.id, message_id=call.message.message_id, reply_markup=markup)
            set_state(call.from_user.id, BotState.CHOOSING_STUDENT, group_id)

        elif call.data.startswith('student_'):
            student_id = int(call.data.split('_')[1])
            student = session.get(Student, student_id)
            if student:
                markup = InlineKeyboardMarkup()
                markup.add(InlineKeyboardButton(text="Опоздал", callback_data=f'late_{student_id}'))
                markup.add(InlineKeyboardButton(text="Отсутствует", callback_data=f'absent_{student_id}'))
                bot.send_message(call.message.chat.id, "Выберите статус студента:", reply_markup=markup)
                set_state(call.from_user.id, BotState.CHOOSING_ACTION, student_id)
            else:
                bot.send_message(call.message.chat.id, "Студент не найден.")

        elif call.data.startswith('late_'):
            student_id = int(call.data.split('_')[1])
            set_state(call.from_user.id, BotState.WAITING_FOR_MINUTES, student_id)
            markup = InlineKeyboardMarkup()
            markup.add(InlineKeyboardButton(text="5 минут", callback_data='minutes_5'))
            markup.add(InlineKeyboardButton(text="10 минут", callback_data='minutes_10'))
            markup.add(InlineKeyboardButton(text="15 минут", callback_data='minutes_15'))
            markup.add(InlineKeyboardButton(text="Ввести вручную", callback_data='minutes_manual'))
            bot.send_message(call.message.chat.id, "Выберите или введите количество минут опоздания:", reply_markup=markup)

        elif call.data.startswith('minutes_'):
            student_id = data
            if 'manual' in call.data:
                bot.send_message(call.message.chat.id, "Введите количество минут опоздания:")
            else:
                minutes = int(call.data.split('_')[1])
                mark_attendance_late(call.message, student_id, minutes)
                set_state(call.from_user.id, BotState.NORMAL)

    except Exception as e:
        bot.send_message(call.message.chat.id, f"Ошибка: {e}")
    finally:
        session.close()
    bot.answer_callback_query(call.id)
def mark_attendance_late(message, student_id, minutes_late):
    session = SessionLocal()
    try:
        attendance = Attendance(date=datetime.now(), status="Опоздал", minutes_late=minutes_late, student_id=student_id)
        session.add(attendance)
        session.commit()
        bot.reply_to(message, f"Опоздание на {minutes_late} минут успешно отмечено.")
    except Exception as e:
        bot.reply_to(message, f"Ошибка: {e}")
    finally:
        session.close()

@bot.message_handler(func=lambda message: get_state(message.from_user.id)[0] == BotState.WAITING_FOR_MINUTES)
def manual_late_minutes_input(message):
    student_id = get_state(message.from_user.id)[1]
    try:
        minutes_late = int(message.text)
        mark_attendance_late(message, student_id, minutes_late)
        set_state(message.from_user.id, BotState.NORMAL)
    except ValueError:
        bot.reply_to(message, "Пожалуйста, введите число. Попробуйте снова.")

@bot.message_handler(commands=['cancel'])
def handle_cancel(message):
    set_state(message.from_user.id, BotState.NORMAL)
    bot.reply_to(message, "Текущее действие отменено.")
    
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
        group_id = add_group(group_name)
        if group_id:
            bot.reply_to(message, f"Группа '{group_name}' успешно добавлена с ID {group_id}.")
        else:
            bot.reply_to(message, "Не удалось добавить группу.")
    except IndexError:
        bot.reply_to(message, "Пожалуйста, укажите название группы после команды /addgroup.")


@bot.message_handler(commands=['addstudents'])
def command_add_students(message):
    session = SessionLocal()
    try:
        groups = session.query(Group).all()
        markup = InlineKeyboardMarkup()
        for group in groups:
            markup.add(InlineKeyboardButton(text=group.name, callback_data=f'addstudent_{group.id}'))
        bot.send_message(message.chat.id, "Выберите группу для добавления студентов:", reply_markup=markup)
    except Exception as e:
        bot.send_message(message.chat.id, f"Ошибка: {e}")
    finally:
        session.close()


# Обработчик для кнопок выбора группы
@bot.callback_query_handler(func=lambda call: call.data.startswith('group_'))
def callback_select_group(call):
    group_id = int(call.data.split('_')[1])
    set_state(call.from_user.id, BotState.CHOOSING_STUDENT, group_id)
    students = session.query(Student).filter(Student.group_id == group_id).all()
    markup = create_students_markup(students)
    bot.edit_message_text("Выберите студента:", chat_id=call.message.chat.id, message_id=call.message.message_id, reply_markup=markup)
    bot.answer_callback_query(call.id)  # Подтверждение обработки

# Обработчик для кнопок добавления студентов
@bot.callback_query_handler(func=lambda call: call.data.startswith('addstudent_'))
def callback_add_students(call):
    group_id = int(call.data.split('_')[1])
    set_state(call.from_user.id, BotState.ADDING_STUDENTS, group_id)
    bot.send_message(call.message.chat.id, "Пожалуйста, отправьте список студентов в формате 'Имя Фамилия', каждый студент на новой строке.")
    bot.answer_callback_query(call.id)  # Подтверждение обработки

# Обработчик для кнопок выбора минут опоздания
@bot.callback_query_handler(func=lambda call: call.data.startswith('minutes_'))
def callback_minutes_late(call):
    student_id, minutes = call.data.split('_')[1:]
    mark_attendance_late(call.message, int(student_id), int(minutes))
    set_state(call.from_user.id, BotState.NORMAL)
    bot.answer_callback_query(call.id)  # Подтверждение обработки

bot.polling(none_stop=True)


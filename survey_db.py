import sqlite3
from sms_db import DB_PATH


def init_survey_db():
    with sqlite3.connect(DB_PATH) as conn:
        c = conn.cursor()
        c.execute('''CREATE TABLE IF NOT EXISTS surveys (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            name TEXT,
            status TEXT
        )''')
        c.execute('''CREATE TABLE IF NOT EXISTS survey_responses (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            survey_id INTEGER,
            contact_id INTEGER,
            response TEXT,
            created_at TEXT DEFAULT CURRENT_TIMESTAMP
        )''')
        c.execute('''CREATE TABLE IF NOT EXISTS survey_questions (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            survey_id INTEGER,
            question_text TEXT,
            qtype TEXT,
            options TEXT
        )''')
        conn.commit()


def add_survey(name, status='active'):
    with sqlite3.connect(DB_PATH) as conn:
        c = conn.cursor()
        c.execute('INSERT INTO surveys (name, status) VALUES (?, ?)', (name, status))
        conn.commit()
        return c.lastrowid


def add_survey_question(survey_id, question_text, qtype='text', options=None):
    with sqlite3.connect(DB_PATH) as conn:
        c = conn.cursor()
        c.execute('INSERT INTO survey_questions (survey_id, question_text, qtype, options) VALUES (?, ?, ?, ?)',
                  (survey_id, question_text, qtype, options))
        conn.commit()


def get_surveys():
    with sqlite3.connect(DB_PATH) as conn:
        c = conn.cursor()
        c.execute('SELECT id, name, status FROM surveys')
        return c.fetchall()


def get_survey_full(survey_id):
    with sqlite3.connect(DB_PATH) as conn:
        c = conn.cursor()
        c.execute('SELECT id, name, status FROM surveys WHERE id=?', (survey_id,))
        survey = c.fetchone()
        c.execute('SELECT id, question_text, qtype, options FROM survey_questions WHERE survey_id=?', (survey_id,))
        questions = c.fetchall()
        return survey, questions


def add_survey_response(survey_id, contact_id, response):
    with sqlite3.connect(DB_PATH) as conn:
        c = conn.cursor()
        c.execute('INSERT INTO survey_responses (survey_id, contact_id, response) VALUES (?, ?, ?)',
                  (survey_id, contact_id, response))
        conn.commit()


def get_survey_responses(survey_id):
    with sqlite3.connect(DB_PATH) as conn:
        c = conn.cursor()
        c.execute('SELECT id, contact_id, response, created_at FROM survey_responses WHERE survey_id=?', (survey_id,))
        return c.fetchall()

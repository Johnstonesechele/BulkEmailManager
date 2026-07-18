import sqlite3
from sms_db import DB_PATH

def add_template(name, content):
    with sqlite3.connect(DB_PATH) as conn:
        c = conn.cursor()
        c.execute('INSERT INTO sms_templates (name, content) VALUES (?, ?)', (name, content))
        conn.commit()

def get_templates():
    with sqlite3.connect(DB_PATH) as conn:
        c = conn.cursor()
        c.execute('SELECT id, name, content FROM sms_templates')
        return c.fetchall()

def get_template_by_id(tid):
    with sqlite3.connect(DB_PATH) as conn:
        c = conn.cursor()
        c.execute('SELECT id, name, content FROM sms_templates WHERE id=?', (tid,))
        return c.fetchone()

def update_template(tid, name, content):
    with sqlite3.connect(DB_PATH) as conn:
        c = conn.cursor()
        c.execute('UPDATE sms_templates SET name=?, content=? WHERE id=?', (name, content, tid))
        conn.commit()

def delete_template(tid):
    with sqlite3.connect(DB_PATH) as conn:
        c = conn.cursor()
        c.execute('DELETE FROM sms_templates WHERE id=?', (tid,))
        conn.commit()

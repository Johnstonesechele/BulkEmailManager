import sqlite3
from sms_db import DB_PATH

def add_email_template(name, subject, html_content, text_content):
    with sqlite3.connect(DB_PATH) as conn:
        c = conn.cursor()
        c.execute('INSERT INTO email_templates (name, subject, html_content, text_content) VALUES (?, ?, ?, ?)',
                  (name, subject, html_content, text_content))
        conn.commit()

def get_email_templates():
    with sqlite3.connect(DB_PATH) as conn:
        c = conn.cursor()
        c.execute('SELECT id, name, subject, html_content, text_content FROM email_templates')
        return c.fetchall()

def get_email_template_by_id(tid):
    with sqlite3.connect(DB_PATH) as conn:
        c = conn.cursor()
        c.execute('SELECT id, name, subject, html_content, text_content FROM email_templates WHERE id=?', (tid,))
        return c.fetchone()

def update_email_template(tid, name, subject, html_content, text_content):
    with sqlite3.connect(DB_PATH) as conn:
        c = conn.cursor()
        c.execute('UPDATE email_templates SET name=?, subject=?, html_content=?, text_content=? WHERE id=?',
                  (name, subject, html_content, text_content, tid))
        conn.commit()

def delete_email_template(tid):
    with sqlite3.connect(DB_PATH) as conn:
        c = conn.cursor()
        c.execute('DELETE FROM email_templates WHERE id=?', (tid,))
        conn.commit()

def add_email_campaign(name, template_id, scheduled_time, status, ab_group=None):
    with sqlite3.connect(DB_PATH) as conn:
        c = conn.cursor()
        c.execute('INSERT INTO email_campaigns (name, template_id, scheduled_time, status, ab_group) VALUES (?, ?, ?, ?, ?)',
                  (name, template_id, scheduled_time, status, ab_group))
        conn.commit()

def get_email_campaigns():
    with sqlite3.connect(DB_PATH) as conn:
        c = conn.cursor()
        c.execute('SELECT id, name, template_id, scheduled_time, status, ab_group FROM email_campaigns')
        return c.fetchall()

def add_email_log(campaign_id, contact_id, status, sent_time, delivery_time=None, error=None):
    with sqlite3.connect(DB_PATH) as conn:
        c = conn.cursor()
        c.execute('INSERT INTO email_logs (campaign_id, contact_id, status, sent_time, delivery_time, error) VALUES (?, ?, ?, ?, ?, ?)',
                  (campaign_id, contact_id, status, sent_time, delivery_time, error))
        conn.commit()

def get_email_logs(campaign_id=None):
    with sqlite3.connect(DB_PATH) as conn:
        c = conn.cursor()
        if campaign_id:
            c.execute('SELECT * FROM email_logs WHERE campaign_id=?', (campaign_id,))
        else:
            c.execute('SELECT * FROM email_logs')
        return c.fetchall()

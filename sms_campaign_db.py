import sqlite3
from sms_db import DB_PATH

def add_sms_campaign(name, template_id, scheduled_time, status, ab_group=None):
    with sqlite3.connect(DB_PATH) as conn:
        c = conn.cursor()
        c.execute('INSERT INTO sms_campaigns (name, template_id, scheduled_time, status, ab_group) VALUES (?, ?, ?, ?, ?)',
                  (name, template_id, scheduled_time, status, ab_group))
        conn.commit()

def get_sms_campaigns():
    with sqlite3.connect(DB_PATH) as conn:
        c = conn.cursor()
        c.execute('SELECT id, name, template_id, scheduled_time, status, ab_group FROM sms_campaigns')
        return c.fetchall()

def add_sms_log(campaign_id, contact_id, status, sent_time, delivery_time=None, error=None):
    with sqlite3.connect(DB_PATH) as conn:
        c = conn.cursor()
        c.execute('INSERT INTO sms_logs (campaign_id, contact_id, status, sent_time, delivery_time, error) VALUES (?, ?, ?, ?, ?, ?)',
                  (campaign_id, contact_id, status, sent_time, delivery_time, error))
        conn.commit()

def get_sms_logs(campaign_id=None):
    with sqlite3.connect(DB_PATH) as conn:
        c = conn.cursor()
        if campaign_id:
            c.execute('SELECT * FROM sms_logs WHERE campaign_id=?', (campaign_id,))
        else:
            c.execute('SELECT * FROM sms_logs')
        return c.fetchall()

def set_setting(key, value):
    with sqlite3.connect(DB_PATH) as conn:
        c = conn.cursor()
        c.execute('INSERT OR REPLACE INTO settings (key, value) VALUES (?, ?)', (key, value))
        conn.commit()

def get_setting(key):
    with sqlite3.connect(DB_PATH) as conn:
        c = conn.cursor()
        c.execute('SELECT value FROM settings WHERE key=?', (key,))
        row = c.fetchone()
        return row[0] if row else None

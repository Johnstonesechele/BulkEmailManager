import sqlite3
from contextlib import closing

DB_PATH = 'bulk_email.db'


def init_db():
    with closing(sqlite3.connect(DB_PATH)) as conn:
        c = conn.cursor()
        c.execute('''CREATE TABLE IF NOT EXISTS contacts (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            name TEXT,
            phone TEXT UNIQUE,
            email TEXT UNIQUE,
            segment TEXT,
            group_name TEXT,
            opt_in INTEGER DEFAULT 1,
            extra TEXT
        )''')
        c.execute('''CREATE TABLE IF NOT EXISTS sms_templates (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            name TEXT,
            content TEXT
        )''')
        c.execute('''CREATE TABLE IF NOT EXISTS email_templates (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            name TEXT,
            subject TEXT,
            html_content TEXT,
            text_content TEXT
        )''')
        c.execute('''CREATE TABLE IF NOT EXISTS sms_campaigns (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            name TEXT,
            template_id INTEGER,
            scheduled_time TEXT,
            status TEXT,
            ab_group TEXT,
            FOREIGN KEY(template_id) REFERENCES sms_templates(id)
        )''')
        c.execute('''CREATE TABLE IF NOT EXISTS email_campaigns (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            name TEXT,
            template_id INTEGER,
            scheduled_time TEXT,
            status TEXT,
            ab_group TEXT,
            FOREIGN KEY(template_id) REFERENCES email_templates(id)
        )''')
        c.execute('''CREATE TABLE IF NOT EXISTS sms_logs (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            campaign_id INTEGER,
            contact_id INTEGER,
            status TEXT,
            sent_time TEXT,
            delivery_time TEXT,
            error TEXT,
            FOREIGN KEY(campaign_id) REFERENCES sms_campaigns(id),
            FOREIGN KEY(contact_id) REFERENCES contacts(id)
        )''')
        c.execute('''CREATE TABLE IF NOT EXISTS email_logs (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            campaign_id INTEGER,
            contact_id INTEGER,
            status TEXT,
            sent_time TEXT,
            delivery_time TEXT,
            error TEXT,
            FOREIGN KEY(campaign_id) REFERENCES email_campaigns(id),
            FOREIGN KEY(contact_id) REFERENCES contacts(id)
        )''')
        c.execute('''CREATE TABLE IF NOT EXISTS feedback (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user TEXT,
            message TEXT,
            created_at TEXT
        )''')
        c.execute('''CREATE TABLE IF NOT EXISTS settings (
            key TEXT PRIMARY KEY,
            value TEXT
        )''')
        conn.commit()

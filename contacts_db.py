import sqlite3
import csv
from sms_db import DB_PATH


def add_contact(name, phone, email=None, segment=None, group_name=None, opt_in=1, extra=None):
    with sqlite3.connect(DB_PATH) as conn:
        c = conn.cursor()
        c.execute('''INSERT OR IGNORE INTO contacts (name, phone, email, segment, group_name, opt_in, extra)
                     VALUES (?, ?, ?, ?, ?, ?, ?)''',
                  (name, phone, email, segment, group_name, opt_in, extra))
        conn.commit()


def get_contacts(segment=None, group_name=None, opt_in_only=True):
    with sqlite3.connect(DB_PATH) as conn:
        c = conn.cursor()
        q = 'SELECT id, name, phone, email, segment, group_name, opt_in, extra FROM contacts WHERE 1=1'
        params = []
        if segment:
            q += ' AND segment=?'
            params.append(segment)
        if group_name:
            q += ' AND group_name=?'
            params.append(group_name)
        if opt_in_only:
            q += ' AND opt_in=1'
        c.execute(q, params)
        return c.fetchall()


def update_opt_in(phone, opt_in):
    with sqlite3.connect(DB_PATH) as conn:
        c = conn.cursor()
        c.execute('UPDATE contacts SET opt_in=? WHERE phone=?', (opt_in, phone))
        conn.commit()


def export_contacts_to_csv(path):
    with sqlite3.connect(DB_PATH) as conn, open(path, 'w', newline='', encoding='utf-8') as f:
        c = conn.cursor()
        c.execute('SELECT name, phone, email, segment, group_name, opt_in, extra FROM contacts')
        writer = csv.writer(f)
        writer.writerow([d[0] for d in c.description])
        writer.writerows(c.fetchall())


def import_contacts_from_csv(path):
    added = 0
    skipped = 0
    with open(path, newline='', encoding='utf-8') as f:
        reader = csv.DictReader(f)
        for row in reader:
            name = row.get('name') or row.get('Name') or ''
            phone = row.get('phone') or row.get('Phone') or ''
            email = row.get('email') or row.get('Email') or row.get('Emails') or ''
            segment = row.get('segment') or row.get('Segment') or ''
            group_name = row.get('group_name') or row.get('Group') or ''
            opt_in = row.get('opt_in', 1)
            extra = row.get('extra') or ''
            if phone or email:
                add_contact(name, phone, email, segment, group_name, opt_in, extra)
                added += 1
            else:
                skipped += 1
    return added, skipped

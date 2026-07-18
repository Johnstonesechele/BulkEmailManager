#!/usr/bin/env python3
# bulk_email.py
# Full-featured GUI (PySide6) for managing contacts, templates, assets, and running bulk email campaigns
# Dark Blue & Dark Gold theme

import os
import sys
import re
import csv
import json
import time
import random
import shutil
import logging
import smtplib
from datetime import datetime
from threading import Thread
import threading

from email.mime.application import MIMEApplication
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText
from email.utils import formataddr

import pandas as pd
from dotenv import load_dotenv
from jinja2 import Environment, FileSystemLoader, StrictUndefined, Undefined
from email_validator import validate_email, EmailNotValidError

# Optional DKIM
try:
    import dkim
except Exception:
    dkim = None

# GUI imports
from PySide6 import QtCore, QtGui, QtWidgets
from PySide6.QtCore import Qt, Signal, QObject
from PySide6.QtGui import QAction
from PySide6.QtWidgets import (
    QApplication, QMainWindow, QWidget, QTabWidget, QVBoxLayout, QHBoxLayout,
    QLabel, QPushButton, QFileDialog, QTableView, QLineEdit, QComboBox, QSpinBox,
    QCheckBox, QProgressBar, QPlainTextEdit, QListWidget, QListWidgetItem,
    QMessageBox, QSplitter, QFormLayout, QTextBrowser
)

from sms_db import init_db

# Initialize database on startup
init_db()
from survey_db import init_survey_db
init_survey_db()

# -----------------------------
# Config & Theme
# -----------------------------
APP_TITLE = "Bulk Email Manager"
DARK_BLUE = "#0B1A39"
DARK_GOLD = "#B8860B"
LIGHT_TEXT = "#EDEFF6"
MID_TEXT = "#C9D1E3"
CARD_BG = "#12224A"
ACCENT = DARK_GOLD

BASE_DIR = os.path.abspath(os.path.dirname(__file__))
EMAILS_DIR = os.path.join(BASE_DIR, "emails")
TEMPLATES_DIR = os.path.join(BASE_DIR, "email-templates")
ASSETS_DIR = os.path.join(BASE_DIR, "assets")
LOG_FILE = os.path.join(BASE_DIR, 'bulk-email-sender.log')

for p in (EMAILS_DIR, TEMPLATES_DIR, ASSETS_DIR):
    os.makedirs(p, exist_ok=True)

# Logging setup
logger = logging.getLogger("bulk_email_gui")
logger.setLevel(logging.INFO)
fh = logging.FileHandler(LOG_FILE)
fh.setLevel(logging.INFO)
ch = logging.StreamHandler()
ch.setLevel(logging.INFO)
fmt = logging.Formatter('%(asctime)s - %(levelname)s - %(message)s')
fh.setFormatter(fmt)
ch.setFormatter(fmt)
logger.addHandler(fh)
logger.addHandler(ch)

# -----------------------------
# Backend: Email Sender (adapted from your script)
# -----------------------------
class BulkEmailSender:
    def __init__(self, smtp_server, smtp_port, username, password, sender_email,
                 sender_name=None,
                 dkim_private_key_path=None, dkim_selector=None, dkim_domain=None,
                 progress_cb=None, log_cb=None, stop_flag_getter=None):
        self.smtp_server = smtp_server
        self.smtp_port = smtp_port
        self.username = username
        self.password = password
        self.sender_email = sender_email
        self.sender_name = sender_name
        self.session = None
        self.connection_attempts = 0
        self.max_connection_attempts = 3
        self.retry_delay = 60
        self.dkim_private_key_path = dkim_private_key_path
        self.dkim_selector = dkim_selector
        self.dkim_domain = dkim_domain
        self.progress_cb = progress_cb
        self.log_cb = log_cb
        self.stop_flag_getter = stop_flag_getter or (lambda: False)

    def _log(self, level, msg):
        if self.log_cb:
            self.log_cb(msg)
        getattr(logger, level)(msg)

    def connect(self):
        try:
            self.connection_attempts += 1
            self.session = smtplib.SMTP(self.smtp_server, self.smtp_port)
            self.session.ehlo()
            self.session.starttls()
            self.session.ehlo()
            self.session.login(self.username, self.password)
            self.connection_attempts = 0
            self._log('info', "Successfully connected to SMTP server")
            return True
        except Exception as e:
            self._log('error', f"Failed to connect to SMTP server: {e}")
            if self.connection_attempts < self.max_connection_attempts:
                self._log('info', f"Retrying in {self.retry_delay} seconds...")
                time.sleep(self.retry_delay)
                return self.connect()
            return False

    def disconnect(self):
        if self.session:
            try:
                self.session.quit()
            except Exception:
                pass
            self.session = None
            self._log('info', "Disconnected from SMTP server")

    def _is_valid_email(self, email):
        try:
            validate_email(email)
            return True
        except EmailNotValidError:
            return False

    def _dkim_sign(self, msg: MIMEMultipart):
        if not (self.dkim_private_key_path and self.dkim_selector and self.dkim_domain and dkim):
            return msg
        try:
            with open(self.dkim_private_key_path, 'rb') as f:
                priv = f.read()
            headers = [b"from", b"to", b"subject", b"date", b"mime-version", b"content-type"]
            sig = dkim.sign(
                message=msg.as_bytes(),
                selector=self.dkim_selector.encode(),
                domain=self.dkim_domain.encode(),
                privkey=priv,
                include_headers=headers
            )
            # Prepend DKIM-Signature header
            signed = sig + msg.as_bytes()
            from email import policy
            from email.parser import BytesParser
            return BytesParser(policy=policy.default).parsebytes(signed)
        except Exception as e:
            self._log('warning', f"DKIM signing failed, sending unsigned. Reason: {e}")
            return msg

    def create_message(self, recipient_email, subject, html_content, text_content=None, attachment_paths=None, cc=None, bcc=None):
        if attachment_paths:
            msg = MIMEMultipart("mixed")
        else:
            msg = MIMEMultipart("alternative")
        msg["Subject"] = subject
        msg["From"] = formataddr((self.sender_name, self.sender_email)) if self.sender_name else self.sender_email
        msg["To"] = recipient_email
        if cc:
            msg["Cc"] = ",".join(cc) if isinstance(cc, list) else str(cc)
        if bcc:
            msg["Bcc"] = ",".join(bcc) if isinstance(bcc, list) else str(bcc)
        # Alternative part for text/html
        alt_part = MIMEMultipart("alternative")
        if text_content:
            alt_part.attach(MIMEText(text_content, "plain"))
        alt_part.attach(MIMEText(html_content, "html"))
        msg.attach(alt_part)
        # Attachments go in the mixed part
        if attachment_paths:
            for file_path in attachment_paths:
                if os.path.exists(file_path):
                    with open(file_path, "rb") as f:
                        attachment = MIMEApplication(f.read(), Name=os.path.basename(file_path))
                        attachment["Content-Disposition"] = f"attachment; filename={os.path.basename(file_path)}"
                        msg.attach(attachment)
                else:
                    self._log('warning', f"Attachment not found: {file_path}")
        return self._dkim_sign(msg)

    def check_gmail_block(self, error_message):
        indicators = [
            "temporary disable", "unusual activity", "unusual sign", "unusual attempt",
            "temporarily locked", "temporary lock", "account has been disabled",
            "account was disabled", "try again later"
        ]
        es = str(error_message).lower()
        return any(ind in es for ind in indicators)

    def send_email(self, msg, recipient_email, cc=None, bcc=None):
        if not self.session:
            if not self.connect():
                return False
        recipients = [recipient_email]
        if cc:
            recipients.extend(cc)
        if bcc:
            recipients.extend(bcc)
        try:
            self.session.send_message(msg, self.sender_email, recipients)
            self._log('info', f"Email sent to {recipient_email}")
            return True
        except Exception as e:
            if self.check_gmail_block(e):
                self._log('error', f"Gmail block detected: {e}")
                self._log('error', "Pausing for 1 hour to avoid account suspension")
                self.session = None
                time.sleep(3600)
                return "BLOCKED"
            if isinstance(e, (smtplib.SMTPServerDisconnected, OSError, ConnectionError)):
                self._log('warning', f"Connection lost to {recipient_email}: {e}")
                self.session = None
                if self.connect():
                    return self.send_email(msg, recipient_email, cc, bcc)
                return False
            self._log('error', f"Failed to send email to {recipient_email}: {e}")
            return False

    def send_bulk_emails(self, df, subject, html_template, text_template=None,
                         attachment_paths=None, personalize=True, delay_base=5,
                         max_emails_per_day=3000, batch_size=25, resume_from=0,
                         save_state=True, state_label="campaign_state.json",
                         jinja_env: Environment | None = None):
        # Pre-validate
        df = df.copy()
        if "Emails" not in df.columns:
            self._log('error', "Invalid data: must contain an 'Emails' column")
            return False
        df = df.dropna(subset=["Emails"])  # basic cleanup
        df["Emails"] = df["Emails"].astype(str).str.strip()
        valid_mask = df["Emails"].apply(self._is_valid_email)
        invalid_count = (~valid_mask).sum()
        if invalid_count:
            self._log('warning', f"Skipping {invalid_count} invalid email addresses")
            df = df[valid_mask]
        if resume_from > 0:
            if resume_from >= len(df):
                self._log('error', f"Resume index {resume_from} exceeds records {len(df)}")
                return False
            df = df.iloc[resume_from:]
            results = {"success": 0, "failed": 0, "skipped": resume_from}
        else:
            results = {"success": 0, "failed": 0, "skipped": 0}
        if len(df) > max_emails_per_day:
            self._log('warning', f"Limiting to {max_emails_per_day} emails per day")
            df = df.head(max_emails_per_day)
        total = len(df)
        if total == 0:
            self._log('info', "No recipients to process.")
            return results
        start_time = datetime.now()
        self._log('info', f"Starting campaign to {total} recipients")
        if not self.connect():
            return False

        # Sending loop
        for i, row in enumerate(df.itertuples(index=False)):
            if self.stop_flag_getter():
                self._log('warning', "Campaign stopped by user")
                break
            rec = getattr(row, 'Emails')

            # Render content
            if personalize and jinja_env is not None:
                context = row._asdict() if hasattr(row, '_asdict') else row._asdict()
                try:
                    html_content = jinja_env.from_string(html_template).render(**context)
                    text_content = jinja_env.from_string(text_template).render(**context) if text_template else None
                except Exception as e:
                    self._log('error', f"Template render error for {rec}: {e}")
                    results["failed"] += 1
                    continue
            else:
                html_content = html_template
                text_content = text_template
                # simple placeholder replacement
                if personalize:
                    for key, val in (row._asdict().items() if hasattr(row, '_asdict') else {}):
                        placeholder = f"{{{{{key}}}}}"
                        sv = "" if pd.isna(val) else str(val)
                        html_content = html_content.replace(placeholder, sv)
                        if text_content:
                            text_content = text_content.replace(placeholder, sv)

            # CC/BCC per row, optional
            cc = []
            if 'cc' in df.columns and pd.notna(getattr(row, 'cc', None)):
                cc = [e.strip() for e in str(getattr(row, 'cc')).split(',') if self._is_valid_email(e.strip())]
            bcc = []
            if 'bcc' in df.columns and pd.notna(getattr(row, 'bcc', None)):
                bcc = [e.strip() for e in str(getattr(row, 'bcc')).split(',') if self._is_valid_email(e.strip())]

            msg = self.create_message(
                recipient_email=rec,
                subject=subject,
                html_content=html_content,
                text_content=text_content,
                attachment_paths=attachment_paths,
                cc=cc or None,
                bcc=bcc or None
            )

            # Progress callback
            if self.progress_cb:
                self.progress_cb(i, total, f"Sending to {rec}...")

            # retry loop
            max_retries = 5
            retry_count = 0
            while retry_count < max_retries:
                result = self.send_email(msg, rec, cc, bcc)
                if result == "BLOCKED":
                    # save state
                    if save_state:
                        try:
                            with open(state_label, 'w') as f:
                                json.dump({"resume_index": i+1, "results": results}, f)
                        except Exception:
                            pass
                    self._log('warning', f"Campaign paused due to provider restrictions. Resume later at index {i+1}")
                    return results
                if result:
                    results["success"] += 1
                    break
                else:
                    retry_count += 1
                    self._log('warning', f"Retry {retry_count}/{max_retries} for {rec}")
                    self.session = None
                    if not self.connect():
                        self._log('error', "Failed to reconnect after retry")
                        results["failed"] += 1
                        break
                    time.sleep(retry_count * 10)
            else:
                results["failed"] += 1

            # pacing
            if i < total - 1:
                time.sleep(5 + random.uniform(0, 5))

            # batch rest
            if (i + 1) % 25 == 0:
                self._log('info', "Taking a short break after 25 emails")
                self.disconnect()
                time.sleep(random.uniform(120, 300))
                if not self.connect():
                    self._log('error', "Failed to reconnect after break")
                    return results

            if self.progress_cb:
                self.progress_cb(i+1, total, f"Sent to {rec}")

        duration = (datetime.now() - start_time).total_seconds()
        self._log('info', f"Campaign completed. Success: {results['success']}, Failed: {results['failed']}, Skipped: {results['skipped']} in {duration:.1f}s")
        self.disconnect()
        return results

# -----------------------------
# Qt Helpers
# -----------------------------
class PandasModel(QtCore.QAbstractTableModel):
    def __init__(self, df=pd.DataFrame(), parent=None):
        super().__init__(parent)
        self._df = df

    def rowCount(self, parent=None):
        return len(self._df.index)

    def columnCount(self, parent=None):
        return len(self._df.columns)

    def data(self, index, role=Qt.DisplayRole):
        if not index.isValid():
            return None
        if role in (Qt.DisplayRole, Qt.EditRole):
            val = self._df.iat[index.row(), index.column()]
            return "" if pd.isna(val) else str(val)
        return None

    def headerData(self, section, orientation, role=Qt.DisplayRole):
        if role != Qt.DisplayRole:
            return None
        if orientation == Qt.Horizontal:
            return str(self._df.columns[section])
        else:
            return str(section)

    def flags(self, index):
        return Qt.ItemIsSelectable | Qt.ItemIsEnabled | Qt.ItemIsEditable

    def setData(self, index, value, role=Qt.EditRole):
        if role == Qt.EditRole:
            self._df.iat[index.row(), index.column()] = value
            self.dataChanged.emit(index, index, [Qt.DisplayRole, Qt.EditRole])
            return True
        return False

    def insertRow(self, position, row_values=None):
        self.beginInsertRows(QtCore.QModelIndex(), position, position)
        if row_values is None:
            row_values = {c: "" for c in self._df.columns}
        self._df = pd.concat([
            self._df.iloc[:position],
            pd.DataFrame([row_values], columns=self._df.columns),
            self._df.iloc[position:]
        ], ignore_index=True)
        self.endInsertRows()
        return True

    def removeRow(self, position):
        self.beginRemoveRows(QtCore.QModelIndex(), position, position)
        self._df = self._df.drop(self._df.index[position]).reset_index(drop=True)
        self.endRemoveRows()
        return True

    def dataframe(self):
        return self._df.copy()

# Signals for worker
class SendSignals(QObject):
    progress = Signal(int, int, str)  # current, total, message
    log = Signal(str)
    done = Signal(dict)

# Worker thread wrapper
class SendWorker(Thread):
    def __init__(self, df, subject, html_content, text_content, attachments, env_file,
                 jinja_strict, dkim_overrides=None, sender_name=None):
        super().__init__()
        self.df = df
        self.subject = subject
        self.html_content = html_content
        self.text_content = text_content
        self.attachments = attachments
        self.env_file = env_file
        self.jinja_strict = jinja_strict
        self.signals = SendSignals()
        self._stop = False
        self.dkim_overrides = dkim_overrides or {}
        self.sender_name = sender_name

    def stop(self):
        self._stop = True

    def send_with_attachments(self, msg):
        if self.attachments:
            for file in self.attachments[:10]:
                try:
                    with open(file, "rb") as f:
                        part = MIMEApplication(f.read(), Name=os.path.basename(file))
                    part['Content-Disposition'] = f'attachment; filename="{os.path.basename(file)}"'
                    msg.attach(part)
                except Exception as e:
                    self.signals.log.emit(f"Failed to attach {file}: {e}")
        return msg

    def run(self):
        # load env
        env_path = os.path.join(BASE_DIR, self.env_file)
        if not os.path.exists(env_path):
            self.signals.log.emit(f"Env file not found: {env_path}")
            self.signals.done.emit({"success": 0, "failed": 0, "skipped": 0})
            return
        # Clear env then load
        for k in list(os.environ.keys()):
            if k.startswith("SMTP_") or k.startswith("DKIM_") or k in ("SENDER_EMAIL", "EMAIL_USERNAME", "EMAIL_PASSWORD", "SENDER_NAME"):
                os.environ.pop(k, None)
        load_dotenv(env_path)
        sender_email = os.getenv('SENDER_EMAIL')
        username = os.getenv('EMAIL_USERNAME')
        password = os.getenv('EMAIL_PASSWORD')
        smtp_server = os.getenv('SMTP_SERVER', 'smtp.gmail.com')
        smtp_port = int(os.getenv('SMTP_PORT', '587'))
        dkim_key = self.dkim_overrides.get('key') or os.getenv('DKIM_PRIVATE_KEY')
        dkim_selector = self.dkim_overrides.get('selector') or os.getenv('DKIM_SELECTOR')
        dkim_domain = self.dkim_overrides.get('domain') or os.getenv('DKIM_DOMAIN')
        sender_name = self.sender_name or os.getenv('SENDER_NAME') or None

        if not all([sender_email, username, password]):
            self.signals.log.emit("Missing SENDER_EMAIL/EMAIL_USERNAME/EMAIL_PASSWORD in env")
            self.signals.done.emit({"success": 0, "failed": 0, "skipped": 0})
            return

        # Jinja environment
        class SafeUndefined(Undefined):
            def _fail_with_undefined_error(self, *args, **kwargs):
                return ""
        jinja_env = Environment(undefined=StrictUndefined if self.jinja_strict else SafeUndefined)

        sender = BulkEmailSender(
            smtp_server=smtp_server,
            smtp_port=smtp_port,
            username=username,
            password=password,
            sender_email=sender_email,
            sender_name=sender_name,
            dkim_private_key_path=dkim_key if dkim_key and os.path.exists(dkim_key) else None,
            dkim_selector=dkim_selector,
            dkim_domain=dkim_domain,
            progress_cb=lambda cur, tot, msg: self.signals.progress.emit(cur, tot, msg),
            log_cb=lambda m: self.signals.log.emit(m),
            stop_flag_getter=lambda: self._stop
        )

        results = sender.send_bulk_emails(
            df=self.df,
            subject=self.subject,
            html_template=self.html_content,
            text_template=self.text_content,
            attachment_paths=self.attachments,
            personalize=True,
            jinja_env=jinja_env
        )
        if not isinstance(results, dict):
            results = {"success": 0, "failed": 0, "skipped": 0}
        self.signals.done.emit(results)
        # If you need to attach files to the message, call self.send_with_attachments(msg) before sending

# -----------------------------
# Tabs
# -----------------------------
class ContactsTab(QWidget):
    def __init__(self, logs_cb):
        super().__init__()
        self.logs_cb = logs_cb
        self.df = pd.DataFrame(columns=["Emails", "FirstName", "LastName", "Segment", "cc", "bcc"])  # default cols
        self.model = PandasModel(self.df)
        self.view = QTableView()
        self.view.setModel(self.model)
        self.view.horizontalHeader().setStretchLastSection(True)
        self.view.setAlternatingRowColors(True)

        self.load_btn = QPushButton("Load CSV")
        self.load_multiple_btn = QPushButton("Load Multiple CSVs")
        self.save_btn = QPushButton("Save CSV")
        self.add_row_btn = QPushButton("Add Row")
        self.del_row_btn = QPushButton("Delete Row")
        self.filter_edit = QLineEdit()
        self.filter_edit.setPlaceholderText("Filter by segment/tag…")

        top = QHBoxLayout()
        top.addWidget(self.load_btn)
        top.addWidget(self.load_multiple_btn)
        top.addWidget(self.save_btn)
        top.addStretch()
        top.addWidget(QLabel("Filter:"))
        top.addWidget(self.filter_edit)
        top.addStretch()
        top.addWidget(self.add_row_btn)
        top.addWidget(self.del_row_btn)

        layout = QVBoxLayout(self)
        layout.addLayout(top)
        layout.addWidget(self.view)

        self.load_btn.clicked.connect(self.load_csv)
        self.load_multiple_btn.clicked.connect(self.load_multiple_csvs)
        self.save_btn.clicked.connect(self.save_csv)
        self.add_row_btn.clicked.connect(self.add_row)
        self.del_row_btn.clicked.connect(self.del_row)
        self.filter_edit.textChanged.connect(self.apply_filter)

        self.current_csv_path = None

    def load_csv(self):
        path, _ = QFileDialog.getOpenFileName(self, "Open Contacts CSV", EMAILS_DIR, "CSV Files (*.csv)")
        if not path:
            return
        try:
            df = pd.read_csv(path)
            if "Emails" not in df.columns:
                raise ValueError("CSV must contain an 'Emails' column")
            self.df = df
            self._original_df = df.copy()
            self.model = PandasModel(self.df)
            self.view.setModel(self.model)
            self.current_csv_path = path
            self.logs_cb(f"Loaded contacts: {path} ({len(df)} rows)")
        except Exception as e:
            QMessageBox.critical(self, "Error", f"Failed to load CSV: {e}")

    def load_multiple_csvs(self):
        paths, _ = QFileDialog.getOpenFileNames(self, "Open Multiple Contacts CSVs", EMAILS_DIR, "CSV Files (*.csv)")
        if not paths:
            return
        try:
            dfs = []
            for path in paths:
                df = pd.read_csv(path)
                if "Emails" not in df.columns:
                    self.logs_cb(f"Warning: Skipping {path} - missing 'Emails' column")
                    continue
                dfs.append(df)
                self.logs_cb(f"Loaded: {path}")
            
            if not dfs:
                QMessageBox.warning(self, "No Valid CSVs", "None of the selected CSV files contain an 'Emails' column.")
                return
            
            # Combine all dataframes
            combined_df = pd.concat(dfs, ignore_index=True)
            
            # Remove duplicates based on email address
            original_count = len(combined_df)
            combined_df = combined_df.drop_duplicates(subset=['Emails'], keep='first')
            deduplicated_count = original_count - len(combined_df)
            
            self.df = combined_df
            self._original_df = combined_df.copy()
            self.model = PandasModel(self.df)
            self.view.setModel(self.model)
            self.current_csv_path = None  # Multiple files, no single path
            
            self.logs_cb(f"Loaded {len(paths)} CSV files with {len(combined_df)} total contacts")
            if deduplicated_count > 0:
                self.logs_cb(f"Removed {deduplicated_count} duplicate email addresses")
        except Exception as e:
            QMessageBox.critical(self, "Error", f"Failed to load CSV files: {e}")

    def save_csv(self):
        if not self.current_csv_path:
            path, _ = QFileDialog.getSaveFileName(self, "Save Contacts CSV", EMAILS_DIR, "CSV Files (*.csv)")
            if not path:
                return
            self.current_csv_path = path
        try:
            self.model.dataframe().to_csv(self.current_csv_path, index=False)
            self.logs_cb(f"Saved contacts: {self.current_csv_path}")
        except Exception as e:
            QMessageBox.critical(self, "Error", f"Failed to save CSV: {e}")

    def add_row(self):
        self.model.insertRow(self.model.rowCount(), None)
        self._original_df = self.model.dataframe()

    def del_row(self):
        idx = self.view.currentIndex()
        if idx.isValid():
            self.model.removeRow(idx.row())
            self._original_df = self.model.dataframe()

    def apply_filter(self, text):
        if not hasattr(self, '_original_df'):
            return
        try:
            df = self._original_df.copy()
            if text.strip():
                mask = pd.Series(False, index=df.index)
                for col in df.columns:
                    mask = mask | df[col].astype(str).str.contains(text, case=False, na=False)
                df = df[mask]
            self.df = df
            self.model = PandasModel(self.df)
            self.view.setModel(self.model)
        except Exception as e:
            self.logs_cb(f"Filter error: {e}")

    def get_dataframe(self):
        return self.model.dataframe()

    def get_current_csv_path(self):
        return self.current_csv_path

class TemplatesTab(QWidget):
    def __init__(self, logs_cb):
        super().__init__()
        self.logs_cb = logs_cb
        self.html_edit = QPlainTextEdit()
        self.txt_edit = QPlainTextEdit()
        self.html_list = QListWidget()
        self.txt_list = QListWidget()
        self.preview = QTextBrowser()

        self.load_html_btn = QPushButton("Load HTML")
        self.save_html_btn = QPushButton("Save HTML")
        self.load_txt_btn = QPushButton("Load TXT")
        self.save_txt_btn = QPushButton("Save TXT")
        self.preview_btn = QPushButton("Preview with Sample Row")

        # Left: lists; Right: editors + preview
        lists_layout = QVBoxLayout()
        lists_layout.addWidget(QLabel("HTML Templates"))
        lists_layout.addWidget(self.html_list)
        lists_layout.addWidget(QLabel("Text Templates"))
        lists_layout.addWidget(self.txt_list)
        lists_layout.addWidget(self.load_html_btn)
        lists_layout.addWidget(self.load_txt_btn)

        editors_layout = QVBoxLayout()
        editors_layout.addWidget(QLabel("HTML Editor"))
        editors_layout.addWidget(self.html_edit)
        editors_layout.addWidget(QLabel("Text Editor"))
        editors_layout.addWidget(self.txt_edit)
        editors_layout.addWidget(self.save_html_btn)
        editors_layout.addWidget(self.save_txt_btn)
        editors_layout.addWidget(self.preview_btn)
        editors_layout.addWidget(QLabel("Preview"))
        editors_layout.addWidget(self.preview)

        splitter = QSplitter()
        left = QWidget(); left.setLayout(lists_layout)
        right = QWidget(); right.setLayout(editors_layout)
        splitter.addWidget(left)
        splitter.addWidget(right)
        splitter.setStretchFactor(1, 3)

        layout = QVBoxLayout(self)
        layout.addWidget(splitter)

        self.load_html_btn.clicked.connect(self.load_html)
        self.save_html_btn.clicked.connect(self.save_html)
        self.load_txt_btn.clicked.connect(self.load_txt)
        self.save_txt_btn.clicked.connect(self.save_txt)
        self.preview_btn.clicked.connect(self.render_preview)
        self.html_list.itemDoubleClicked.connect(self.select_html)
        self.txt_list.itemDoubleClicked.connect(self.select_txt)

        self.refresh_lists()

    def refresh_lists(self):
        self.html_list.clear(); self.txt_list.clear()
        for f in sorted(os.listdir(TEMPLATES_DIR)):
            path = os.path.join(TEMPLATES_DIR, f)
            if os.path.isfile(path):
                if f.lower().endswith('.html'):
                    self.html_list.addItem(f)
                elif f.lower().endswith('.txt'):
                    self.txt_list.addItem(f)

    def load_html(self):
        path, _ = QFileDialog.getOpenFileName(self, "Open HTML Template", TEMPLATES_DIR, "HTML Files (*.html)")
        if not path:
            return
        try:
            with open(path, 'r', encoding='utf-8') as f:
                self.html_edit.setPlainText(f.read())
            self.logs_cb(f"Loaded HTML template: {path}")
            self.refresh_lists()
        except Exception as e:
            QMessageBox.critical(self, "Error", f"Failed to load HTML: {e}")

    def save_html(self):
        path, _ = QFileDialog.getSaveFileName(self, "Save HTML Template", TEMPLATES_DIR, "HTML Files (*.html)")
        if not path:
            return
        try:
            with open(path, 'w', encoding='utf-8') as f:
                f.write(self.html_edit.toPlainText())
            self.logs_cb(f"Saved HTML template: {path}")
            self.refresh_lists()
        except Exception as e:
            QMessageBox.critical(self, "Error", f"Failed to save HTML: {e}")

    def load_txt(self):
        path, _ = QFileDialog.getOpenFileName(self, "Open Text Template", TEMPLATES_DIR, "Text Files (*.txt)")
        if not path:
            return
        try:
            with open(path, 'r', encoding='utf-8') as f:
                self.txt_edit.setPlainText(f.read())
            self.logs_cb(f"Loaded text template: {path}")
            self.refresh_lists()
        except Exception as e:
            QMessageBox.critical(self, "Error", f"Failed to load TXT: {e}")

    def save_txt(self):
        path, _ = QFileDialog.getSaveFileName(self, "Save Text Template", TEMPLATES_DIR, "Text Files (*.txt)")
        if not path:
            return
        try:
            with open(path, 'w', encoding='utf-8') as f:
                f.write(self.txt_edit.toPlainText())
            self.logs_cb(f"Saved text template: {path}")
            self.refresh_lists()
        except Exception as e:
            QMessageBox.critical(self, "Error", f"Failed to save TXT: {e}")

    def select_html(self, item: QListWidgetItem):
        path = os.path.join(TEMPLATES_DIR, item.text())
        try:
            with open(path, 'r', encoding='utf-8') as f:
                self.html_edit.setPlainText(f.read())
        except Exception as e:
            QMessageBox.critical(self, "Error", f"Failed to open: {e}")

    def select_txt(self, item: QListWidgetItem):
        path = os.path.join(TEMPLATES_DIR, item.text())
        try:
            with open(path, 'r', encoding='utf-8') as f:
                self.txt_edit.setPlainText(f.read())
        except Exception as e:
            QMessageBox.critical(self, "Error", f"Failed to open: {e}")

    def render_preview(self):
        # Use dummy sample
        sample = {"Emails": "jane.doe@example.com", "FirstName": "Jane", "LastName": "Doe", "Segment": "Test"}
        class SafeUndefined(Undefined):
            def _fail_with_undefined_error(self, *args, **kwargs):
                return ""
        env = Environment(undefined=SafeUndefined)
        html = env.from_string(self.html_edit.toPlainText()).render(**sample)
        self.preview.setHtml(html)

    def get_templates(self):
        return self.html_edit.toPlainText(), self.txt_edit.toPlainText()

class AssetsTab(QWidget):
    def __init__(self, logs_cb):
        super().__init__()
        self.logs_cb = logs_cb
        self.list = QListWidget()
        self.list.setSelectionMode(QListWidget.MultiSelection)  # Allow multiple selection
        self.add_btn = QPushButton("Add Files")
        self.del_btn = QPushButton("Remove Selected")
        self.open_btn = QPushButton("Open")

        top = QHBoxLayout()
        top.addWidget(self.add_btn)
        top.addWidget(self.del_btn)
        top.addStretch()
        top.addWidget(self.open_btn)

        layout = QVBoxLayout(self)
        layout.addLayout(top)
        layout.addWidget(self.list)

        self.add_btn.clicked.connect(self.add_files)
        self.del_btn.clicked.connect(self.remove_selected)
        self.open_btn.clicked.connect(self.open_selected)

        self.refresh()

    def refresh(self):
        self.list.clear()
        for root, _, files in os.walk(ASSETS_DIR):
            for f in files:
                rel = os.path.relpath(os.path.join(root, f), ASSETS_DIR)
                self.list.addItem(rel)

    def add_files(self):
        files, _ = QFileDialog.getOpenFileNames(self, "Add Assets", BASE_DIR, "All Files (*)")
        for f in files:
            try:
                dest = os.path.join(ASSETS_DIR, os.path.basename(f))
                if os.path.abspath(f) != os.path.abspath(dest):
                    shutil.copy2(f, dest)
                self.logs_cb(f"Added asset: {dest}")
            except Exception as e:
                QMessageBox.critical(self, "Error", f"Failed to add asset: {e}")
        self.refresh()

    def remove_selected(self):
        items = self.list.selectedItems()
        if not items:
            return
        for it in items:
            path = os.path.join(ASSETS_DIR, it.text())
            try:
                os.remove(path)
                self.logs_cb(f"Removed asset: {path}")
            except Exception as e:
                QMessageBox.critical(self, "Error", f"Failed to remove asset: {e}")
        self.refresh()

    def open_selected(self):
        items = self.list.selectedItems()
        if not items:
            return
        path = os.path.join(ASSETS_DIR, items[0].text())
        QtGui.QDesktopServices.openUrl(QtCore.QUrl.fromLocalFile(path))

    def get_selected_assets(self):
        items = self.list.selectedItems()
        if len(items) > 10:
            QMessageBox.warning(self, "Attachment limit",
                            "You can only select up to 10 attachments.")
        # ✅ return only the first 10
        items = items[:10]
        return [os.path.join(ASSETS_DIR, it.text()) for it in items]


class CampaignTab(QWidget):
    def __init__(self, contacts_tab: ContactsTab, templates_tab: TemplatesTab, assets_tab: AssetsTab, logs_cb):
        super().__init__()
        self.contacts_tab = contacts_tab
        self.templates_tab = templates_tab
        self.assets_tab = assets_tab
        self.logs_cb = logs_cb

        # Controls
        self.env_combo = QComboBox()
        env_files = sorted(f for f in os.listdir(BASE_DIR) if f.startswith(".env.") and not f.endswith(".example") and os.path.isfile(os.path.join(BASE_DIR, f)))
        if env_files:
            self.env_combo.addItems(env_files)
        else:
            self.env_combo.addItem("No .env files found")
            self.env_combo.setEnabled(False)
        self.sender_name_edit = QLineEdit(); self.sender_name_edit.setPlaceholderText("e.g. Ascent Institutes (optional)")
        self.subject_edit = QLineEdit(); self.subject_edit.setPlaceholderText("Email subject…")
        self.jinja_strict = QCheckBox("Jinja strict mode (error on missing vars)")
        self.segment_col_edit = QLineEdit(); self.segment_col_edit.setPlaceholderText("Segment column name, e.g., Segment")
        self.include_segments_edit = QLineEdit(); self.include_segments_edit.setPlaceholderText("Include segments: A,B")
        self.exclude_segments_edit = QLineEdit(); self.exclude_segments_edit.setPlaceholderText("Exclude segments: Test")
        self.preview_btn = QPushButton("Preview for a Random Contact")
        self.start_btn = QPushButton("Start Sending")
        self.stop_btn = QPushButton("Stop")
        self.progress = QProgressBar()
        self.status_lbl = QLabel("Idle")

        form = QFormLayout()
        form.addRow("Environment:", self.env_combo)
        form.addRow("Sender Name:", self.sender_name_edit)
        form.addRow("Subject:", self.subject_edit)
        form.addRow("Segment column:", self.segment_col_edit)
        form.addRow("Include:", self.include_segments_edit)
        form.addRow("Exclude:", self.exclude_segments_edit)
        form.addRow("Mode:", self.jinja_strict)

        buttons = QHBoxLayout()
        buttons.addWidget(self.preview_btn)
        buttons.addStretch()
        buttons.addWidget(self.start_btn)
        buttons.addWidget(self.stop_btn)

        layout = QVBoxLayout(self)
        layout.addLayout(form)
        layout.addWidget(QLabel("Attachments (select in Assets tab; use Ctrl/Shift):"))
        layout.addWidget(self.progress)
        layout.addWidget(self.status_lbl)
        layout.addLayout(buttons)

        self.preview_btn.clicked.connect(self.preview_email)
        self.start_btn.clicked.connect(self.start_sending)
        self.stop_btn.clicked.connect(self.stop_sending)
        self.attachments_list = QListWidget()
        self.attachments_list.setSelectionMode(QListWidget.NoSelection)  # just for display
        layout.addWidget(self.attachments_list)

        self.worker: SendWorker | None = None

    def _apply_segmentation(self, df: pd.DataFrame) -> pd.DataFrame:
        seg_col = self.segment_col_edit.text().strip()
        inc = [s.strip() for s in self.include_segments_edit.text().split(',') if s.strip()]
        exc = [s.strip() for s in self.exclude_segments_edit.text().split(',') if s.strip()]
        if seg_col and seg_col in df.columns:
            if inc:
                df = df[df[seg_col].astype(str).isin(inc)]
            if exc:
                df = df[~df[seg_col].astype(str).isin(exc)]
        return df

    def preview_email(self):
        df = self.contacts_tab.get_dataframe()
        df = self._apply_segmentation(df)
        if df.empty:
            QMessageBox.warning(self, "No contacts", "Your filtered contacts are empty.")
            return
        row = df.sample(1).iloc[0].to_dict()
        html_t, txt_t = self.templates_tab.get_templates()
        class SafeUndefined(Undefined):
            def _fail_with_undefined_error(self, *args, **kwargs):
                return ""
        env = Environment(undefined=StrictUndefined if self.jinja_strict.isChecked() else SafeUndefined)
        try:
            html = env.from_string(html_t).render(**row)
        except Exception as e:
            QMessageBox.critical(self, "Template Error", f"HTML render error: {e}")
            return
        dlg = QtWidgets.QDialog(self)
        dlg.setWindowTitle("Preview")
        lay = QVBoxLayout(dlg)
        view = QTextBrowser(); view.setHtml(html)
        lay.addWidget(view)
        close = QPushButton("Close"); close.clicked.connect(dlg.accept)
        lay.addWidget(close)
        dlg.resize(800, 600)
        dlg.exec()

    def start_sending(self):
        if self.worker and self.worker.is_alive():
            QMessageBox.information(self, "Busy", "A campaign is already running.")
            return
        subject = self.subject_edit.text().strip()
        if not subject:
            QMessageBox.warning(self, "Subject missing", "Please enter an email subject.")
            return
        df = self.contacts_tab.get_dataframe()
        df = self._apply_segmentation(df)
        if df.empty:
            QMessageBox.warning(self, "No contacts", "Your filtered contacts are empty.")
            return
        html_t, txt_t = self.templates_tab.get_templates()
        if not html_t.strip():
            QMessageBox.warning(self, "Template missing", "Please provide an HTML template.")
            return

        # attachments are optional; enforce max 10 if any are selected
        assets = self.assets_tab.get_selected_assets()
        if len(assets) > 10:
            QMessageBox.warning(self, "Too many attachments", "You can only send up to 10 attachments.")
            assets = assets[:10]
        self.attachments_list.clear()
        for f in assets:
            self.attachments_list.addItem(os.path.basename(f))

        env_file = self.env_combo.currentText()
        sender_name = self.sender_name_edit.text().strip() or None
        self.progress.setValue(0)
        self.status_lbl.setText("Starting…")
        self.start_btn.setEnabled(False)

        self.worker = SendWorker(
            df=df,
            subject=subject,
            html_content=html_t,
            text_content=txt_t if txt_t.strip() else None,
            attachments=assets,  # guaranteed 0–4 files
            env_file=env_file,
            jinja_strict=self.jinja_strict.isChecked(),
            sender_name=sender_name,
        )
        self.worker.signals.progress.connect(self.on_progress)
        self.worker.signals.log.connect(self.logs_cb)
        self.worker.signals.done.connect(self.on_done)
        self.worker.start()

    def on_progress(self, cur, tot, msg):
        pct = int((cur / max(1, tot)) * 100)
        self.progress.setValue(pct)
        self.status_lbl.setText(msg)

    def on_done(self, results: dict):
        self.progress.setValue(100)
        self.status_lbl.setText("Completed")
        self.start_btn.setEnabled(True)
        success = results.get('success', 0)
        failed = results.get('failed', 0)
        skipped = results.get('skipped', 0)
        total = success + failed + skipped
        QMessageBox.information(
            self, "Campaign Finished",
            f"Total: {total}\nSuccess: {success}\nFailed: {failed}\nSkipped: {skipped}"
        )

    def stop_sending(self):
        if self.worker and self.worker.is_alive():
            self.worker.stop()
            self.status_lbl.setText("Stopping…")
            self.start_btn.setEnabled(True)

class LogsTab(QWidget):
    def __init__(self):
        super().__init__()
        self.view = QPlainTextEdit(); self.view.setReadOnly(True)
        layout = QVBoxLayout(self)
        layout.addWidget(self.view)

    def append(self, text: str):
        ts = datetime.now().strftime('%H:%M:%S')
        self.view.appendPlainText(f"[{ts}] {text}")

class AnalyticsTab(QWidget):
    def __init__(self, logs_cb):
        super().__init__()
        self.logs_cb = logs_cb
        self.tabs = QTabWidget()
        self.email_analytics = QTextBrowser(); self.sms_analytics = QTextBrowser(); self.survey_analytics = QTextBrowser()
        self.tabs.addTab(self.email_analytics, "Email Analytics")
        self.tabs.addTab(self.sms_analytics, "SMS Analytics")
        self.tabs.addTab(self.survey_analytics, "Survey Analytics")
        layout = QVBoxLayout(self)
        layout.addWidget(self.tabs)
        self.refresh_btn = QPushButton("Refresh All")
        layout.addWidget(self.refresh_btn)
        self.refresh_btn.clicked.connect(self.refresh)
        self.refresh()
    def refresh(self):
        # Email analytics
        try:
            from email_db import get_email_logs
            logs = get_email_logs()
            self.email_analytics.setPlainText(f"Total email logs: {len(logs)}\n" + '\n'.join(str(l) for l in logs[:20]))
        except Exception as e:
            self.email_analytics.setPlainText(f"Error: {e}")
        # SMS analytics
        try:
            from sms_campaign_db import get_sms_logs
            logs = get_sms_logs()
            self.sms_analytics.setPlainText(f"Total SMS logs: {len(logs)}\n" + '\n'.join(str(l) for l in logs[:20]))
        except Exception as e:
            self.sms_analytics.setPlainText(f"Error: {e}")
        # Survey analytics
        try:
            from survey_db import get_surveys, get_survey_responses
            surveys = get_surveys()
            summary = []
            for sid, name, status in surveys:
                responses = get_survey_responses(sid)
                summary.append(f"Survey: {name} ({status}) - {len(responses)} responses")
            self.survey_analytics.setPlainText('\n'.join(summary))
        except Exception as e:
            self.survey_analytics.setPlainText(f"Error: {e}")

class BulkSMSTab(QWidget):
    def __init__(self, logs_cb):
        super().__init__()
        self.logs_cb = logs_cb
        self.port_combo = QComboBox()
        self.refresh_ports_btn = QPushButton("Refresh Ports")
        self.numbers_edit = QPlainTextEdit()
        self.message_edit = QPlainTextEdit()
        self.send_btn = QPushButton("Send Bulk SMS")
        self.progress = QProgressBar()
        self.status_lbl = QLabel("")

        port_layout = QHBoxLayout()
        port_layout.addWidget(QLabel("GSM Modem Port:"))
        port_layout.addWidget(self.port_combo)
        port_layout.addWidget(self.refresh_ports_btn)

        layout = QVBoxLayout(self)
        layout.addLayout(port_layout)
        layout.addWidget(QLabel("Recipient Numbers (one per line):"))
        layout.addWidget(self.numbers_edit)
        layout.addWidget(QLabel("Message:"))
        layout.addWidget(self.message_edit)
        layout.addWidget(self.send_btn)
        layout.addWidget(self.progress)
        layout.addWidget(self.status_lbl)
        self.send_btn.clicked.connect(self.send_bulk_sms)
        self.refresh_ports_btn.clicked.connect(self.refresh_ports)
        self.refresh_ports()

    def refresh_ports(self):
        self.port_combo.clear()
        try:
            from serial.tools.list_ports import comports
            ports = [p.device for p in comports()]
            self.port_combo.addItems(ports)
            if not ports:
                self.status_lbl.setText("No serial ports detected. Connect a GSM modem.")
        except ImportError:
            self.status_lbl.setText("pyserial not installed. Run: pip install pyserial")

    def send_bulk_sms(self):
        from gsm_sender import GSMSender
        port = self.port_combo.currentText()
        if not port:
            QMessageBox.warning(self, "No Port", "Please select a GSM modem port.")
            return
        numbers = [n.strip() for n in self.numbers_edit.toPlainText().splitlines() if n.strip()]
        message = self.message_edit.toPlainText().strip()
        if not numbers or not message:
            QMessageBox.warning(self, "Missing Data", "Please enter phone numbers and a message.")
            return
        self.progress.setValue(0)
        self.status_lbl.setText("Sending...")
        self.send_btn.setEnabled(False)
        sender = GSMSender(port=port)
        def progress_cb(cur, tot, msg):
            pct = int((cur / max(1, tot)) * 100)
            self.progress.setValue(pct)
            self.status_lbl.setText(msg)
        threading.Thread(target=self._send_thread, args=(sender, numbers, message, progress_cb), daemon=True).start()

    def _send_thread(self, sender, numbers, message, progress_cb):
        try:
            results = sender.send_bulk_sms(numbers, message, progress_cb)
            sent = sum(1 for r in results.values() if r and 'OK' in str(r))
            self.status_lbl.setText(f"Done. Sent: {sent}/{len(numbers)}")
            self.logs_cb(f"Bulk SMS results: {results}")
        except Exception as e:
            self.status_lbl.setText(f"Error: {e}")
            self.logs_cb(f"Bulk SMS error: {e}")
        finally:
            self.send_btn.setEnabled(True)

class ContactsDBTab(QWidget):
    def __init__(self, logs_cb):
        super().__init__()
        from contacts_db import get_contacts, add_contact, update_opt_in, import_contacts_from_csv, export_contacts_to_csv
        self.logs_cb = logs_cb
        self.get_contacts = get_contacts
        self.add_contact = add_contact
        self.update_opt_in = update_opt_in
        self.import_contacts_from_csv = import_contacts_from_csv
        self.export_contacts_to_csv = export_contacts_to_csv

        self.table = QTableView()
        self.model = QtGui.QStandardItemModel()
        self.table.setModel(self.model)
        self.table.setSelectionBehavior(QTableView.SelectRows)
        self.table.setEditTriggers(QTableView.NoEditTriggers)
        self.refresh_btn = QPushButton("Refresh")
        self.import_btn = QPushButton("Import CSV")
        self.export_btn = QPushButton("Export CSV")
        self.add_btn = QPushButton("Add Contact")
        self.optin_btn = QPushButton("Opt-in")
        self.optout_btn = QPushButton("Opt-out")
        top = QHBoxLayout()
        top.addWidget(self.refresh_btn)
        top.addWidget(self.import_btn)
        top.addWidget(self.export_btn)
        top.addWidget(self.add_btn)
        top.addWidget(self.optin_btn)
        top.addWidget(self.optout_btn)
        layout = QVBoxLayout(self)
        layout.addLayout(top)
        layout.addWidget(self.table)
        self.refresh_btn.clicked.connect(self.refresh)
        self.import_btn.clicked.connect(self.import_csv)
        self.export_btn.clicked.connect(self.export_csv)
        self.add_btn.clicked.connect(self.add_contact_dialog)
        self.optin_btn.clicked.connect(lambda: self.set_opt(1))
        self.optout_btn.clicked.connect(lambda: self.set_opt(0))
        self.refresh()

    def refresh(self):
        self.model.clear()
        self.model.setHorizontalHeaderLabels(["ID", "Name", "Phone", "Email", "Segment", "Group", "Opt-in", "Extra"])
        for row in self.get_contacts(opt_in_only=False):
            self.model.appendRow([QtGui.QStandardItem(str(x)) for x in row])

    def import_csv(self):
        path, _ = QFileDialog.getOpenFileName(self, "Import Contacts CSV", EMAILS_DIR, "CSV Files (*.csv)")
        if path:
            added, skipped = self.import_contacts_from_csv(path)
            self.logs_cb(f"Imported {added} contacts from {path} ({skipped} skipped)")
            self.refresh()

    def export_csv(self):
        path, _ = QFileDialog.getSaveFileName(self, "Export Contacts CSV", EMAILS_DIR, "CSV Files (*.csv)")
        if path:
            self.export_contacts_to_csv(path)
            self.logs_cb(f"Exported contacts to {path}")

    def add_contact_dialog(self):
        dlg = QtWidgets.QDialog(self)
        dlg.setWindowTitle("Add Contact")
        form = QFormLayout(dlg)
        name = QLineEdit(); phone = QLineEdit(); email = QLineEdit(); segment = QLineEdit(); group = QLineEdit()
        form.addRow("Name", name); form.addRow("Phone", phone); form.addRow("Email", email)
        form.addRow("Segment", segment); form.addRow("Group", group)
        ok = QPushButton("Add"); ok.clicked.connect(dlg.accept)
        form.addRow(ok)
        if dlg.exec() == QtWidgets.QDialog.Accepted:
            if not phone.text().strip() and not email.text().strip():
                QMessageBox.warning(self, "Missing Data", "Please enter at least a phone number or email.")
                return
            self.add_contact(name.text(), phone.text(), email.text(), segment.text(), group.text())
            self.logs_cb(f"Added contact {name.text()} ({phone.text() or email.text()})")
            self.refresh()

    def set_opt(self, val):
        idx = self.table.currentIndex()
        if not idx.isValid():
            QMessageBox.warning(self, "No Selection", "Please select a contact first.")
            return
        phone = self.model.item(idx.row(), 2).text()
        self.update_opt_in(phone, val)
        self.logs_cb(f"Set opt-in={val} for {phone}")
        self.refresh()

class SMSTemplatesTab(QWidget):
    def __init__(self, logs_cb):
        super().__init__()
        from templates_db import get_templates, add_template, update_template, delete_template
        self.logs_cb = logs_cb
        self.get_templates = get_templates
        self.add_template = add_template
        self.update_template = update_template
        self.delete_template = delete_template
        self.list = QListWidget()
        self.edit = QPlainTextEdit()
        self.name_edit = QLineEdit()
        self.save_btn = QPushButton("Save")
        self.add_btn = QPushButton("Add New")
        self.del_btn = QPushButton("Delete")
        top = QHBoxLayout()
        top.addWidget(self.name_edit)
        top.addWidget(self.add_btn)
        top.addWidget(self.save_btn)
        top.addWidget(self.del_btn)
        layout = QVBoxLayout(self)
        layout.addLayout(top)
        layout.addWidget(self.list)
        layout.addWidget(QLabel("Template Content (use {name}, {phone}, etc.):"))
        layout.addWidget(self.edit)
        self.list.itemClicked.connect(self.load_template)
        self.save_btn.clicked.connect(self.save)
        self.add_btn.clicked.connect(self.add)
        self.del_btn.clicked.connect(self.delete)
        self.refresh()

    def refresh(self):
        self.list.clear()
        for tid, name, content in self.get_templates():
            item = QListWidgetItem(f"{name} (ID:{tid})")
            item.setData(Qt.UserRole, (tid, name, content))
            self.list.addItem(item)

    def load_template(self, item):
        tid, name, content = item.data(Qt.UserRole)
        self.name_edit.setText(name)
        self.edit.setPlainText(content)
        self.current_tid = tid

    def save(self):
        if not hasattr(self, 'current_tid'):
            QMessageBox.warning(self, "No Selection", "Please select a template to update.")
            return
        name = self.name_edit.text().strip()
        content = self.edit.toPlainText().strip()
        if not name:
            QMessageBox.warning(self, "Missing Name", "Please enter a template name.")
            return
        if not content:
            QMessageBox.warning(self, "Missing Content", "Please enter template content.")
            return
        self.update_template(self.current_tid, name, content)
        self.logs_cb(f"Updated template {name}")
        self.refresh()

    def add(self):
        name = self.name_edit.text().strip()
        content = self.edit.toPlainText().strip()
        if not name:
            QMessageBox.warning(self, "Missing Name", "Please enter a template name.")
            return
        if not content:
            QMessageBox.warning(self, "Missing Content", "Please enter template content.")
            return
        self.add_template(name, content)
        self.logs_cb(f"Added template {name}")
        self.refresh()

    def delete(self):
        if not hasattr(self, 'current_tid'):
            QMessageBox.warning(self, "No Selection", "Please select a template to delete.")
            return
        reply = QMessageBox.question(self, "Confirm Delete", f"Delete template '{self.name_edit.text()}'?")
        if reply == QMessageBox.Yes:
            self.delete_template(self.current_tid)
            self.logs_cb(f"Deleted template {self.name_edit.text()}")
            self.refresh()

class EmailTemplatesTab(QWidget):
    def __init__(self, logs_cb):
        super().__init__()
        from email_db import get_email_templates, add_email_template, update_email_template, delete_email_template
        self.logs_cb = logs_cb
        self.get_templates = get_email_templates
        self.add_template = add_email_template
        self.update_template = update_email_template
        self.delete_template = delete_email_template
        self.list = QListWidget()
        self.name_edit = QLineEdit()
        self.subject_edit = QLineEdit()
        self.html_edit = QPlainTextEdit()
        self.text_edit = QPlainTextEdit()
        self.save_btn = QPushButton("Save")
        self.add_btn = QPushButton("Add New")
        self.del_btn = QPushButton("Delete")
        top = QHBoxLayout()
        top.addWidget(self.name_edit)
        top.addWidget(self.subject_edit)
        top.addWidget(self.add_btn)
        top.addWidget(self.save_btn)
        top.addWidget(self.del_btn)
        layout = QVBoxLayout(self)
        layout.addLayout(top)
        layout.addWidget(self.list)
        layout.addWidget(QLabel("HTML Content:"))
        layout.addWidget(self.html_edit)
        layout.addWidget(QLabel("Text Content:"))
        layout.addWidget(self.text_edit)
        self.list.itemClicked.connect(self.load_template)
        self.save_btn.clicked.connect(self.save)
        self.add_btn.clicked.connect(self.add)
        self.del_btn.clicked.connect(self.delete)
        self.refresh()

    def refresh(self):
        self.list.clear()
        for tid, name, subject, html, text in self.get_templates():
            item = QListWidgetItem(f"{name} (ID:{tid})")
            item.setData(Qt.UserRole, (tid, name, subject, html, text))
            self.list.addItem(item)

    def load_template(self, item):
        tid, name, subject, html, text = item.data(Qt.UserRole)
        self.name_edit.setText(name)
        self.subject_edit.setText(subject)
        self.html_edit.setPlainText(html)
        self.text_edit.setPlainText(text)
        self.current_tid = tid

    def save(self):
        if not hasattr(self, 'current_tid'):
            QMessageBox.warning(self, "No Selection", "Please select a template to update.")
            return
        name = self.name_edit.text().strip()
        subject = self.subject_edit.text().strip()
        html = self.html_edit.toPlainText().strip()
        if not name:
            QMessageBox.warning(self, "Missing Name", "Please enter a template name.")
            return
        if not subject:
            QMessageBox.warning(self, "Missing Subject", "Please enter an email subject.")
            return
        if not html:
            QMessageBox.warning(self, "Missing HTML", "Please enter HTML content.")
            return
        self.update_template(self.current_tid, name, subject, html, self.text_edit.toPlainText())
        self.logs_cb(f"Updated email template {name}")
        self.refresh()

    def add(self):
        name = self.name_edit.text().strip()
        subject = self.subject_edit.text().strip()
        html = self.html_edit.toPlainText().strip()
        if not name:
            QMessageBox.warning(self, "Missing Name", "Please enter a template name.")
            return
        if not subject:
            QMessageBox.warning(self, "Missing Subject", "Please enter an email subject.")
            return
        if not html:
            QMessageBox.warning(self, "Missing HTML", "Please enter HTML content.")
            return
        self.add_template(name, subject, html, self.text_edit.toPlainText())
        self.logs_cb(f"Added email template {name}")
        self.refresh()

    def delete(self):
        if not hasattr(self, 'current_tid'):
            QMessageBox.warning(self, "No Selection", "Please select a template to delete.")
            return
        reply = QMessageBox.question(self, "Confirm Delete", f"Delete template '{self.name_edit.text()}'?")
        if reply == QMessageBox.Yes:
            self.delete_template(self.current_tid)
            self.logs_cb(f"Deleted email template {self.name_edit.text()}")
            self.refresh()

class SurveyResponseForm(QtWidgets.QDialog):
    def __init__(self, survey_id, parent=None):
        super().__init__(parent)
        from survey_db import get_survey_full, add_survey_response
        self.setWindowTitle("Submit Survey Response")
        self.survey_id = survey_id
        survey, questions = get_survey_full(survey_id)
        self.questions = questions
        self.responses = {}
        layout = QFormLayout(self)
        self.inputs = {}
        for qid, qtext, qtype, qopts in questions:
            if qtype == "text":
                inp = QLineEdit()
            elif qtype == "multiple choice":
                inp = QComboBox(); inp.addItems([o.strip() for o in (qopts or '').split(',') if o.strip()])
            elif qtype == "checkbox":
                inp = QListWidget(); inp.setSelectionMode(QListWidget.MultiSelection)
                for o in (qopts or '').split(','):
                    if o.strip(): inp.addItem(o.strip())
            else:
                inp = QLineEdit()
            layout.addRow(qtext, inp)
            self.inputs[qid] = inp
        self.contact_id = QLineEdit(); layout.addRow("Contact ID", self.contact_id)
        submit = QPushButton("Submit"); submit.clicked.connect(self.submit)
        layout.addRow(submit)
        self.add_survey_response = add_survey_response
    def submit(self):
        for qid, inp in self.inputs.items():
            if isinstance(inp, QLineEdit):
                resp = inp.text()
            elif isinstance(inp, QComboBox):
                resp = inp.currentText()
            elif isinstance(inp, QListWidget):
                resp = ','.join([item.text() for item in inp.selectedItems()])
            else:
                resp = str(inp.text())
            self.add_survey_response(self.survey_id, self.contact_id.text(), f"Q{qid}:{resp}")
        self.accept()

class SurveyTab(QWidget):
    def __init__(self, logs_cb):
        super().__init__()
        from survey_db import get_surveys, add_survey, get_survey_responses
        self.logs_cb = logs_cb
        self.get_surveys = get_surveys
        self.add_survey = add_survey
        self.get_survey_responses = get_survey_responses
        self.list = QListWidget()
        self.add_btn = QPushButton("Add Survey")
        self.refresh_btn = QPushButton("Refresh")
        self.responses_btn = QPushButton("Show Responses")
        self.submit_btn = QPushButton("Submit Response")
        top = QHBoxLayout()
        top.addWidget(self.add_btn)
        top.addWidget(self.refresh_btn)
        top.addWidget(self.responses_btn)
        top.addWidget(self.submit_btn)
        layout = QVBoxLayout(self)
        layout.addLayout(top)
        layout.addWidget(self.list)
        self.add_btn.clicked.connect(self.add_survey_dialog)
        self.refresh_btn.clicked.connect(self.refresh)
        self.responses_btn.clicked.connect(self.show_responses)
        self.submit_btn.clicked.connect(self.submit_response)
        self.refresh()

    def refresh(self):
        self.list.clear()
        for sid, name, status in self.get_surveys():
            item = QListWidgetItem(f"{name} [{status}]")
            item.setData(Qt.UserRole, (sid, name, status))
            self.list.addItem(item)

    def add_survey_dialog(self):
        dlg = QtWidgets.QDialog(self)
        dlg.setWindowTitle("Add Survey")
        form = QFormLayout(dlg)
        name = QLineEdit()
        form.addRow("Survey Name", name)
        questions = []
        questions_list = QListWidget()
        add_q_btn = QPushButton("Add Question")
        def add_question():
            qdlg = QtWidgets.QDialog(dlg)
            qdlg.setWindowTitle("Add Question")
            qform = QFormLayout(qdlg)
            qtext = QLineEdit(); qtype = QComboBox(); qtype.addItems(["text", "multiple choice", "checkbox"])
            qopts = QLineEdit(); qopts.setPlaceholderText("Comma separated options (if applicable)")
            qform.addRow("Question", qtext)
            qform.addRow("Type", qtype)
            qform.addRow("Options", qopts)
            ok = QPushButton("Add"); ok.clicked.connect(qdlg.accept)
            qform.addRow(ok)
            if qdlg.exec() == QtWidgets.QDialog.Accepted:
                questions.append((qtext.text(), qtype.currentText(), qopts.text()))
                questions_list.addItem(f"{qtext.text()} [{qtype.currentText()}] {qopts.text()}")
        add_q_btn.clicked.connect(add_question)
        form.addRow(add_q_btn)
        form.addRow(questions_list)
        ok = QPushButton("Create Survey"); ok.clicked.connect(dlg.accept)
        form.addRow(ok)
        if dlg.exec() == QtWidgets.QDialog.Accepted:
            if not name.text().strip():
                QMessageBox.warning(self, "Missing Name", "Please enter a survey name.")
                return
            if not questions:
                QMessageBox.warning(self, "No Questions", "Please add at least one question.")
                return
            from survey_db import add_survey, add_survey_question
            sid = add_survey(name.text())
            for qtext, qtype, qopts in questions:
                add_survey_question(sid, qtext, qtype, qopts)
            self.logs_cb(f"Added survey {name.text()} with {len(questions)} questions")
            self.refresh()

    def show_responses(self):
        idx = self.list.currentRow()
        if idx < 0:
            QMessageBox.warning(self, "No Survey", "Please select a survey first.")
            return
        sid, name, status = self.list.item(idx).data(Qt.UserRole)
        from survey_db import get_survey_full, get_survey_responses
        survey, questions = get_survey_full(sid)
        responses = get_survey_responses(sid)
        dlg = QtWidgets.QDialog(self)
        dlg.setWindowTitle(f"Responses for {name}")
        dlg.resize(600, 500)
        main_layout = QVBoxLayout(dlg)
        # Questions section
        main_layout.addWidget(QLabel("Questions:"))
        for qid, qtext, qtype, qopts in questions:
            main_layout.addWidget(QLabel(f"  {qtext} [{qtype}] {qopts or ''}"))
        # Responses section in a scroll area
        main_layout.addWidget(QLabel(f"Responses ({len(responses)}):"))
        scroll = QtWidgets.QScrollArea()
        scroll_widget = QWidget()
        scroll_layout = QVBoxLayout(scroll_widget)
        if responses:
            for rid, contact_id, response, created_at in responses:
                scroll_layout.addWidget(QLabel(f"  Contact {contact_id}: {response} ({created_at})"))
        else:
            scroll_layout.addWidget(QLabel("  No responses yet."))
        scroll_layout.addStretch()
        scroll.setWidget(scroll_widget)
        scroll.setWidgetResizable(True)
        main_layout.addWidget(scroll)
        close = QPushButton("Close"); close.clicked.connect(dlg.accept)
        main_layout.addWidget(close)
        dlg.exec()

    def submit_response(self):
        idx = self.list.currentRow()
        if idx < 0:
            QMessageBox.warning(self, "No Survey", "Please select a survey first.")
            return
        sid, name, status = self.list.item(idx).data(Qt.UserRole)
        dlg = SurveyResponseForm(sid, self)
        dlg.exec()

# -----------------------------#
# Main Window                  #
# -----------------------------#
class MainWindow(QMainWindow):
    def __init__(self):
        super().__init__()
        self.setWindowTitle(APP_TITLE)
        self.resize(1200, 800)

        self.logs_tab = LogsTab()
        self.contacts_tab = ContactsTab(self.logs_tab.append)
        self.contacts_db_tab = ContactsDBTab(self.logs_tab.append)
        self.templates_tab = TemplatesTab(self.logs_tab.append)
        self.sms_templates_tab = SMSTemplatesTab(self.logs_tab.append)
        self.email_templates_tab = EmailTemplatesTab(self.logs_tab.append)
        self.assets_tab = AssetsTab(self.logs_tab.append)
        self.campaign_tab = CampaignTab(self.contacts_tab, self.templates_tab, self.assets_tab, self.logs_tab.append)
        self.bulk_sms_tab = BulkSMSTab(self.logs_tab.append)
        self.analytics_tab = AnalyticsTab(self.logs_tab.append)
        self.survey_tab = SurveyTab(self.logs_tab.append)

        tabs = QTabWidget()
        tabs.addTab(self.contacts_tab, "Contacts (Email)")
        tabs.addTab(self.contacts_db_tab, "Contacts (SMS)")
        tabs.addTab(self.templates_tab, "Email Templates (Legacy)")
        tabs.addTab(self.email_templates_tab, "Email Templates (DB)")
        tabs.addTab(self.sms_templates_tab, "SMS Templates")
        tabs.addTab(self.assets_tab, "Assets")
        tabs.addTab(self.campaign_tab, "Campaign")
        tabs.addTab(self.bulk_sms_tab, "Bulk SMS")
        tabs.addTab(self.analytics_tab, "Analytics")
        tabs.addTab(self.survey_tab, "Surveys")
        tabs.addTab(self.logs_tab, "Logs")

        self.setCentralWidget(tabs)
        self._apply_styles()
        self._build_menu()

    def _build_menu(self):
        bar = self.menuBar()
        file_menu = bar.addMenu("File")
        quit_act = QAction("Quit", self)
        quit_act.triggered.connect(self.close)
        file_menu.addAction(quit_act)

        help_menu = bar.addMenu("Help")
        about_act = QAction("About", self)
        about_act.triggered.connect(lambda: QMessageBox.information(self, "About", "Bulk Email Manager\nDark Blue & Dark Gold Theme"))
        help_menu.addAction(about_act)

    def _apply_styles(self):
        self.setStyleSheet(f"""
            QMainWindow, QWidget {{ background-color: {DARK_BLUE}; color: {LIGHT_TEXT}; }}
            QMenuBar {{ background-color: {CARD_BG}; color: {LIGHT_TEXT}; }}
            QMenuBar::item:selected {{ background: {ACCENT}; }}
            QTabWidget::pane {{ border: 1px solid {ACCENT}; }}
            QTabBar::tab {{ background: {CARD_BG}; color: {LIGHT_TEXT}; padding: 8px 16px; border: 1px solid {DARK_BLUE}; border-bottom: none; }}
            QTabBar::tab:selected {{ background: {DARK_BLUE}; border-color: {ACCENT}; }}
            QPushButton {{ background-color: {ACCENT}; color: #0b0b0b; border: none; padding: 8px 14px; border-radius: 8px; font-weight: 600; }}
            QPushButton:hover {{ filter: brightness(1.1); }}
            QLineEdit, QPlainTextEdit, QTextBrowser, QListWidget, QTableView {{
                background-color: {CARD_BG}; color: {LIGHT_TEXT}; border: 1px solid {ACCENT}; border-radius: 6px; selection-background-color: {ACCENT};
            }}
            QLabel {{ color: {MID_TEXT}; }}
            QProgressBar {{ border: 1px solid {ACCENT}; border-radius: 6px; text-align: center; }}
            QProgressBar::chunk {{ background-color: {ACCENT}; }}
        """)

# -----------------------------
# Entry
# -----------------------------
def main():
    app = QApplication(sys.argv)
    win = MainWindow()
    win.show()
    sys.exit(app.exec())

if __name__ == "__main__":
    main()

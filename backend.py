import argparse
import json
import logging
import os
import random
import smtplib
import time
import re
import sys
from datetime import datetime
from email.mime.application import MIMEApplication
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText
from email.utils import formatdate, make_msgid
from typing import List, Optional

import pandas as pd
from dotenv import load_dotenv

# New: Jinja2 templating
from jinja2 import Environment, FileSystemLoader, StrictUndefined, Template

# New: DKIM signing
try:
    import dkim
except Exception:
    dkim = None

#############################################
# Logging setup
#############################################
console_handler = logging.StreamHandler()
console_handler.setLevel(logging.INFO)
file_handler = logging.FileHandler('bulk-email-sender.log')
file_handler.setLevel(logging.INFO)
formatter = logging.Formatter('%(asctime)s - %(levelname)s - %(message)s')
console_handler.setFormatter(formatter)
file_handler.setFormatter(formatter)
logger = logging.getLogger()
logger.setLevel(logging.INFO)
logger.addHandler(console_handler)
logger.addHandler(file_handler)

#############################################
# Helpers
#############################################

def _read_file(path: str) -> Optional[str]:
    if not path:
        return None
    if not os.path.exists(path):
        logging.error(f"File not found: {path}")
        return None
    with open(path, 'r', encoding='utf-8') as f:
        return f.read()


def load_email_template(template_path):
    return _read_file(template_path)


def load_environment(env_name):
    env_file = f".env.{env_name}"
    if not os.path.exists(env_file):
        logging.error(f"Environment file '{env_file}' does not exist")
        logging.error("Available environments: it, pension, governance")
        sys.exit(1)
    # Only clear email-related env vars, not all env vars
    for k in list(os.environ.keys()):
        if k.startswith("SMTP_") or k.startswith("DKIM_") or k in ("SENDER_EMAIL", "EMAIL_USERNAME", "EMAIL_PASSWORD", "SENDER_NAME"):
            os.environ.pop(k, None)
    load_dotenv(env_file)
    sender_email = os.getenv('SENDER_EMAIL')
    username = os.getenv('EMAIL_USERNAME')
    password = os.getenv('EMAIL_PASSWORD')
    if not all([sender_email, username, password]):
        logging.error("Missing environment variables: EMAIL_USERNAME, EMAIL_PASSWORD, or SENDER_EMAIL")
        sys.exit(1)
    logging.info(f"Loaded environment: {env_name}")
    logging.info(f"Sender: {sender_email}")
    return sender_email, username, password


def get_csv_list(env):
    csv_lists = {
        'it': [
            "emails/June 4th Cleaned/test.csv",
            "emails/June 4th Cleaned/Companies_Emails.csv",
            "emails/June 4th Cleaned/Counties_Emails.csv",
            "emails/June 4th Cleaned/Credit_Lending_Facilities_Emails.csv",
            "emails/June 4th Cleaned/Emabssies_Emails.csv",
            "emails/June 4th Cleaned/Ghana_Banks.csv",
            "emails/June 4th Cleaned/Hospitals_Emails.csv",
            "emails/June 4th Cleaned/GOK_Ministries.csv",
            "emails/June 4th Cleaned/HRs.csv",
            "emails/June 4th Cleaned/Managing_Directors_Emails.csv",
            "emails/June 4th Cleaned/Microfinance_Emails.csv",
            "emails/June 4th Cleaned/Noted_Emails.csv",
            "emails/June 4th Cleaned/Parastatals_Emails.csv",
            "emails/June 4th Cleaned/Sacco_Emails.csv",
            "emails/June 4th Cleaned/Private_Hospitals.csv",
            "emails/June 4th Cleaned/Schools_Emails.csv",
            "emails/June 4th Cleaned/Security_Firms.csv",
        ],
        'pension': [
            "emails/may/may-19/pension_emails.csv",
            "emails/may/may-19/pension_additional.csv",
            "emails/may/may-19/pension_supplementary.csv",
        ],
        'governance': [
            "emails/may/may-19/governance_emails.csv",
            "emails/may/may-19/governance_extra.csv",
            "emails/may/may-19/governance_new.csv",
        ],
    }
    return csv_lists.get(env, [])

#############################################
# Jinja2 Template Rendering
#############################################
class TemplateRenderer:
    def __init__(self, template_dir: str = ".", strict: bool = False):
        undefined = StrictUndefined if strict else None
        self.env = Environment(
            loader=FileSystemLoader(template_dir),
            autoescape=False,
            undefined=undefined,
            trim_blocks=True,
            lstrip_blocks=True,
        )

    def render_from_string(self, template_str: str, context: dict) -> str:
        tmpl: Template = self.env.from_string(template_str)
        return tmpl.render(**context)

#############################################
# CSV Segmentation
#############################################

def segment_dataframe(df: pd.DataFrame, segment_col: Optional[str], include: Optional[List[str]], exclude: Optional[List[str]]) -> pd.DataFrame:
    if segment_col and segment_col in df.columns:
        if include:
            df = df[df[segment_col].astype(str).isin(include)]
        if exclude:
            df = df[~df[segment_col].astype(str).isin(exclude)]
    return df

#############################################
# Email Sender (with DKIM)
#############################################
class BulkEmailSender:
    def __init__(self, smtp_server, smtp_port, username, password, sender_email,
                 dkim_private_key_path: Optional[str] = None,
                 dkim_selector: Optional[str] = None,
                 dkim_domain: Optional[str] = None):
        self.smtp_server = smtp_server
        self.smtp_port = smtp_port
        self.username = username
        self.password = password
        self.sender_email = sender_email
        self.session = None
        self.connection_attempts = 0
        self.max_connection_attempts = 3
        self.retry_delay = 60

        # DKIM
        self.dkim_private_key_path = dkim_private_key_path
        self.dkim_selector = dkim_selector
        self.dkim_domain = dkim_domain
        self._dkim_key: Optional[bytes] = None
        if self.dkim_enabled and dkim is None:
            logging.warning("dkimpy package not available; DKIM disabled.")

    @property
    def dkim_enabled(self) -> bool:
        return bool(self.dkim_private_key_path and self.dkim_selector and self.dkim_domain and dkim is not None)

    def _ensure_dkim_key(self):
        if self.dkim_enabled and self._dkim_key is None:
            if not os.path.exists(self.dkim_private_key_path):
                logging.error(f"DKIM private key not found: {self.dkim_private_key_path}")
                return
            with open(self.dkim_private_key_path, 'rb') as f:
                self._dkim_key = f.read()

    def connect(self):
        try:
            self.connection_attempts += 1
            self.session = smtplib.SMTP(self.smtp_server, self.smtp_port)
            self.session.ehlo()
            self.session.starttls()
            self.session.ehlo()
            self.session.login(self.username, self.password)
            self.connection_attempts = 0
            logging.info("Successfully connected to SMTP server")
            return True
        except Exception as e:
            logging.error(f"Failed to connect to SMTP server: {e}")
            if self.connection_attempts < self.max_connection_attempts:
                logging.info(f"Retrying in {self.retry_delay} seconds...")
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
            logging.info("Disconnected from SMTP server")

    def _is_valid_email(self, email):
        email_pattern = r'^[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}$'
        return bool(re.match(email_pattern, email))

    def _attach_files(self, msg: MIMEMultipart, attachment_paths: Optional[List[str]]):
        if not attachment_paths:
            return
        for file_path in attachment_paths:
            if os.path.exists(file_path):
                with open(file_path, 'rb') as f:
                    part = MIMEApplication(f.read(), Name=os.path.basename(file_path))
                    part['Content-Disposition'] = f'attachment; filename={os.path.basename(file_path)}'
                    msg.attach(part)
            else:
                logging.warning(f"Attachment not found: {file_path}")

    def _build_message(self, recipient_email: str, subject: str, html_content: str,
                        text_content: Optional[str] = None,
                        attachment_paths: Optional[List[str]] = None,
                        cc: Optional[List[str]] = None,
                        bcc: Optional[List[str]] = None) -> MIMEMultipart:
        msg = MIMEMultipart("alternative")
        msg['Subject'] = subject
        msg['From'] = self.sender_email
        msg['To'] = recipient_email
        if cc:
            msg['Cc'] = ','.join(cc)
        if bcc:
            msg['Bcc'] = ','.join(bcc)
        msg['Date'] = formatdate(localtime=True)
        msg['Message-ID'] = make_msgid()

        if text_content:
            msg.attach(MIMEText(text_content, 'plain', 'utf-8'))
        msg.attach(MIMEText(html_content, 'html', 'utf-8'))
        self._attach_files(msg, attachment_paths)
        return msg

    def _dkim_sign(self, msg_bytes: bytes) -> Optional[bytes]:
        if not self.dkim_enabled:
            return None
        self._ensure_dkim_key()
        if not self._dkim_key:
            return None
        include_headers = [b"from", b"to", b"cc", b"subject", b"date", b"message-id", b"mime-version", b"content-type", b"content-transfer-encoding"]
        try:
            sig = dkim.sign(
                message=msg_bytes,
                selector=self.dkim_selector.encode('utf-8'),
                domain=self.dkim_domain.encode('utf-8'),
                privkey=self._dkim_key,
                include_headers=include_headers,
                canonicalize=(b'relaxed', b'relaxed'),
            )
            # Prepend DKIM-Signature header to the message
            return sig + msg_bytes
        except Exception as e:
            logging.error(f"Failed to DKIM-sign message: {e}")
            return None

    def check_gmail_block(self, error_message):
        block_indicators = [
            "temporary disable", "unusual activity", "unusual sign", "unusual attempt",
            "temporarily locked", "temporary lock", "account has been disabled",
            "account was disabled", "try again later",
        ]
        error_str = str(error_message).lower()
        return any(ind in error_str for ind in block_indicators)

    def send_email(self, msg: MIMEMultipart, recipient_email: str, cc=None, bcc=None):
        if not self.session:
            if not self.connect():
                return False
        recipients = [recipient_email]
        if cc:
            recipients.extend(cc)
        if bcc:
            recipients.extend(bcc)
        try:
            if self.dkim_enabled:
                raw = msg.as_bytes()
                signed = self._dkim_sign(raw)
                if signed is None:
                    # Fall back to unsigned
                    logging.warning("Proceeding without DKIM signature")
                    self.session.send_message(msg, self.sender_email, recipients)
                else:
                    self.session.sendmail(self.sender_email, recipients, signed)
            else:
                self.session.send_message(msg, self.sender_email, recipients)
            logging.info(f"Email sent to {recipient_email}")
            return True
        except Exception as e:
            if self.check_gmail_block(e):
                logging.error(f"Gmail block detected: {e}")
                logging.error("Pausing for 1 hour to avoid account suspension")
                self.session = None
                time.sleep(3600)
                return "BLOCKED"
            if isinstance(e, (smtplib.SMTPServerDisconnected, OSError, ConnectionError)):
                logging.warning(f"Connection lost to {recipient_email}: {e}")
                self.session = None
                if self.connect():
                    return self.send_email(msg, recipient_email, cc, bcc)
                return False
            logging.error(f"Failed to send email to {recipient_email}: {e}")
            return False

    def send_bulk_emails(self, csv_file, subject, html_template, text_template=None, attachment_paths=None,
                         personalize=True, delay_base=5, max_emails_per_day=450,
                         batch_size=25, resume_from=0, save_state=True,
                         segment_col: Optional[str] = None, include_segments: Optional[List[str]] = None,
                         exclude_segments: Optional[List[str]] = None,
                         use_jinja: bool = True, jinja_strict: bool = False):
        # Validate inputs
        if not os.path.exists(csv_file):
            logging.error(f"CSV file not found: {csv_file}")
            return False
        if not html_template:
            logging.error("HTML template is empty or failed to load")
            return False
        if text_template is None:
            logging.warning("No text template provided; proceeding with HTML only")
        if attachment_paths:
            for path in attachment_paths:
                if not os.path.exists(path):
                    logging.error(f"Missing attachment: {path}")
                    return False
            logging.info(f"Confirmed {len(attachment_paths)} attachments: {', '.join(attachment_paths)}")
        else:
            logging.info("No attachments specified")

        try:
            df = pd.read_csv(csv_file)
            if "Emails" not in df.columns:
                logging.error("Invalid CSV file, must contain an 'Emails' column")
                return False
            df = df.dropna(subset=["Emails"]).copy()
            df["Emails"] = df["Emails"].astype(str).str.strip()
            valid_emails = df["Emails"].apply(self._is_valid_email)
            invalid_count = (~valid_emails).sum()
            if invalid_count > 0:
                logging.warning(f"Skipping {invalid_count} invalid email addresses")
                df = df[valid_emails]

            # Segmentation
            df = segment_dataframe(df, segment_col, include_segments, exclude_segments)

            if resume_from > 0:
                if resume_from >= len(df):
                    logging.error(f"Resume index {resume_from} is greater than the number of records {len(df)}")
                    return False
                logging.info(f"Resuming campaign from record {resume_from} for {csv_file}")
                skipped_records = df.iloc[:resume_from]
                results = {"success": 0, "failed": 0, "skipped": len(skipped_records)}
                df = df.iloc[resume_from:]
            else:
                results = {"success": 0, "failed": 0, "skipped": 0}

            if len(df) > max_emails_per_day:
                logging.warning(f"Limiting to {max_emails_per_day} emails per day, due to Gmail's daily sending limit")
                df = df.head(max_emails_per_day)

            total_recipients = len(df)
            if total_recipients == 0:
                logging.info(f"No recipients to process in {csv_file}")
                return results

            start_time = datetime.now()
            logging.info(f"Starting bulk email campaign to {total_recipients} recipients for {csv_file}")
            state_file = f"email_campaign_state_{os.path.basename(csv_file)}_{start_time.strftime('%Y%m%d_%H%M%S')}.json"

            # Prepare templating
            renderer = TemplateRenderer(template_dir=os.path.dirname(os.path.abspath(csv_file)) or '.', strict=jinja_strict)

            if not self.connect():
                return False

            for index, row in df.iterrows():
                real_index = int(row.name)  # original index from CSV
                recipient_email = row["Emails"]

                if save_state:
                    self._save_campaign_state(state_file, real_index, results)

                # Collect CC/BCC if present
                cc = None
                if 'cc' in df.columns and pd.notna(row.get('cc')):
                    cc = [e.strip() for e in str(row.get('cc')).split(',') if e.strip()]
                    cc = [e for e in cc if self._is_valid_email(e)] or None

                bcc = None
                if 'bcc' in df.columns and pd.notna(row.get('bcc')):
                    bcc = [e.strip() for e in str(row.get('bcc')).split(',') if e.strip()]
                    bcc = [e for e in bcc if self._is_valid_email(e)] or None

                # Build context from row
                context = {k: ("" if pd.isna(v) else v) for k, v in row.to_dict().items()}

                if personalize:
                    if use_jinja:
                        personalized_html = renderer.render_from_string(html_template, context)
                        personalized_text = renderer.render_from_string(text_template, context) if text_template else None
                    else:
                        # Plain {{key}} replacement fallback
                        personalized_html = html_template
                        personalized_text = text_template if text_template else None
                        for key, value in context.items():
                            placeholder = f"{{{{{key}}}}}"
                            personalized_html = personalized_html.replace(placeholder, str(value))
                            if personalized_text:
                                personalized_text = personalized_text.replace(placeholder, str(value))
                else:
                    personalized_html = html_template
                    personalized_text = text_template

                msg = self._build_message(
                    recipient_email=recipient_email,
                    subject=subject,
                    html_content=personalized_html,
                    text_content=personalized_text,
                    attachment_paths=attachment_paths,
                    cc=cc,
                    bcc=bcc,
                )

                progress = f"Processing email {index + 1}/{total_recipients} ({(index + 1) / total_recipients * 100:.1f}%) for {csv_file}"
                print(f"\r{progress}", end="", flush=True)

                max_retries = 5
                retry_count = 0
                while retry_count < max_retries:
                    result = self.send_email(msg, recipient_email, cc, bcc)
                    if result == "BLOCKED":
                        if save_state:
                            self._save_campaign_state(state_file, real_index + 1, results)
                        logging.warning(f"Campaign paused due to Gmail restrictions for {csv_file}. Resume later with --resume {real_index + 1}")
                        return results
                    if result:
                        results["success"] += 1
                        logging.info(f"✓ Sent to {recipient_email}")
                        break
                    else:
                        retry_count += 1
                        logging.warning(f"Failed to send to {recipient_email}, retry {retry_count}/{max_retries}")
                        self.session = None
                        if not self.connect():
                            logging.error("Failed to reconnect to SMTP server after retry")
                            results["failed"] += 1
                            break
                        time.sleep(retry_count * 10)
                else:
                    results["failed"] += 1
                    logging.error(f"✗ Failed to send to {recipient_email} after {max_retries} retries")

                current_delay = delay_base + random.uniform(0, 5)
                if index < total_recipients - 1:
                    time.sleep(current_delay)

                if (index + 1) % batch_size == 0:
                    logging.info(f"Taking a break after {batch_size} emails")
                    self.disconnect()
                    time.sleep(random.uniform(120, 300))
                    if not self.connect():
                        logging.error("Failed to reconnect to SMTP server after break")
                        return results

            end_time = datetime.now()
            duration = (end_time - start_time).total_seconds()
            logging.info(f"Bulk email campaign completed for {csv_file} in {duration:.2f} seconds")
            logging.info(f"Results: {results['success']} successful, {results['failed']} failed, {results['skipped']} skipped")
            print("\n")
            summary = (
                f"\nBulk email campaign completed for {csv_file}:"
                f"\n- Duration: {duration:.2f} seconds"
                f"\n- Successful: {results['success']}"
                f"\n- Failed: {results['failed']}"
                f"\n- Skipped: {results['skipped']}"
            )
            logging.info(summary)
            return results

        except Exception as e:
            logging.error(f"Error in bulk email process for {csv_file}: {str(e)}")
            return False
        finally:
            self.disconnect()

    def _save_campaign_state(self, state_file, resume_index, results):
        state = {"resume_index": resume_index, "results": results}
        try:
            with open(state_file, 'w') as f:
                json.dump(state, f)
            logging.info(f"Campaign state saved to {state_file}")
        except Exception as e:
            logging.error(f"Failed to save campaign state to {state_file}: {e}")

#############################################
# Orchestration helpers
#############################################

def confirm_campaign_details(csv_list, subjects, html_templates, text_templates, attachments_list,
                             smtp_server, smtp_port, sender_email, resume_from,
                             env_name='it', is_post_test=False):
    title = "Post-test Confirmation for Remaining CSVs" if is_post_test else "Bulk Email Campaign Details for All CSVs"
    print(f"\n=== {title} ===")
    logging.info(f"=== {title} ===")
    all_valid = True
    for csv_index, csv in enumerate(csv_list):
        print(f"\nCSV {csv_index + 1}/{len(csv_list)}: {csv}")
        logging.info(f"CSV {csv_index + 1}/{len(csv_list)}: {csv}")
        logging.info(f"Current working directory: {os.getcwd()}")
        logging.info(f"Current date and time: {datetime.now().strftime('%I:%M %p %Z, %A, %B %d, %Y')}")
        logging.info(f"Environment: {env_name}")
        logging.info(f"CSV file: {csv}")
        if not os.path.exists(csv):
            logging.error(f"CSV file not found: {csv}")
            print(f"ERROR: CSV file not found: {csv}")
            all_valid = False
            continue
        logging.info(f"Subject: {subjects[csv_index]}")
        print(f"Subject: {subjects[csv_index]}")
        if not subjects[csv_index]:
            logging.error("Subject is empty")
            print("ERROR: Subject is empty")
            all_valid = False
        logging.info(f"HTML template: {'Loaded' if html_templates[csv_index] else 'Not loaded'}")
        print(f"HTML template: {'Loaded' if html_templates[csv_index] else 'Not loaded'}")
        if not html_templates[csv_index]:
            logging.error("HTML template is empty or failed to load")
            print("ERROR: HTML template is empty or failed to load")
            all_valid = False
        logging.info(f"Text template: {'Loaded' if text_templates[csv_index] else 'Not provided'}")
        print(f"Text template: {'Loaded' if text_templates[csv_index] else 'Not provided'}")
        if text_templates[csv_index] is None:
            logging.warning("No text template provided; proceeding with HTML only")
            print("WARNING: No text template provided; proceeding with HTML only")
        if attachments_list[csv_index]:
            logging.info(f"Attachments ({len(attachments_list[csv_index])}): {', '.join(attachments_list[csv_index])}")
            print(f"Attachments ({len(attachments_list[csv_index])}): {', '.join(attachments_list[csv_index])}")
            for path in attachments_list[csv_index]:
                if not os.path.exists(path):
                    logging.error(f"Missing attachment: {path}")
                    print(f"ERROR: Missing attachment: {path}")
                    all_valid = False
        else:
            logging.info("No attachments specified")
            print("No attachments specified")
        logging.info(f"SMTP server: {smtp_server}:{smtp_port}")
        print(f"SMTP server: {smtp_server}:{smtp_port}")
        logging.info(f"Sender email: {sender_email}")
        print(f"Sender email: {sender_email}")
        logging.info(f"Resume from index: {resume_from}")
        print(f"Resume from index: {resume_from}")

    if not all_valid:
        logging.error("One or more validation errors occurred. Aborting campaign.")
        print("ERROR: One or more validation errors occurred. Aborting campaign.")
        return False

    prompt = (
        "Review the emails sent from test.csv. Type 'yes' to proceed with sending remaining campaigns, or any other key to abort:" if is_post_test
        else "All details for all CSVs verified. Type 'yes' to proceed with sending all campaigns, or any other key to abort:"
    )
    print(f"\n{prompt}")
    confirmation = input().strip().lower()
    logging.info(f"User confirmation response: {confirmation}")
    if confirmation != 'yes':
        logging.warning("Campaign aborted by user")
        print("Campaign aborted.")
        return False
    logging.info(f"User confirmed: proceeding with {'remaining CSVs' if is_post_test else 'email campaign for all CSVs'}")
    return True


def email_sender(subject, files, custom_html_template, custom_text_template, smtp_server, smtp_port,
                 username, password, sender_email, csv_file,
                 resume_from: int = 0,
                 segment_col: Optional[str] = None,
                 include_segments: Optional[List[str]] = None,
                 exclude_segments: Optional[List[str]] = None,
                 use_jinja: bool = True,
                 jinja_strict: bool = False,
                 dkim_private_key: Optional[str] = None,
                 dkim_selector: Optional[str] = None,
                 dkim_domain: Optional[str] = None):
    if not subject:
        logging.error("Subject is empty")
        return False, None
    logging.info(f"Email subject: {subject}")
    logging.info(f"CSV file: {csv_file}")
    sender = BulkEmailSender(
        smtp_server=smtp_server,
        smtp_port=smtp_port,
        username=username,
        password=password,
        sender_email=sender_email,
        dkim_private_key_path=dkim_private_key,
        dkim_selector=dkim_selector,
        dkim_domain=dkim_domain,
    )
    final_results = sender.send_bulk_emails(
        csv_file=csv_file,
        subject=subject,
        html_template=custom_html_template,
        text_template=custom_text_template,
        attachment_paths=files,
        personalize=True,
        delay_base=5,
        max_emails_per_day=450,
        batch_size=25,
        resume_from=resume_from,
        segment_col=segment_col,
        include_segments=include_segments,
        exclude_segments=exclude_segments,
        use_jinja=use_jinja,
        jinja_strict=jinja_strict,
    )
    return final_results, sender

#############################################
# Main
#############################################
if __name__ == "__main__":
    parser = argparse.ArgumentParser(description='Bulk Email Sender (Jinja2 + Segmentation + DKIM)')
    parser.add_argument('-e', '--env', choices=['it', 'pension', 'governance'], default='it', help='Environment to use (default: it)')
    parser.add_argument('--resume', type=int, default=0, help='Resume campaign from a specific index')

    # Jinja & Segmentation controls
    parser.add_argument('--no-jinja', action='store_true', help='Disable Jinja2 templating (fallback to {{var}} replacement)')
    parser.add_argument('--jinja-strict', action='store_true', help='Fail if a template variable is undefined')
    parser.add_argument('--segment-col', type=str, default=None, help='CSV column name containing segment labels/tags')
    parser.add_argument('--include-segments', type=str, default=None, help='Comma-separated list of segments to include')
    parser.add_argument('--exclude-segments', type=str, default=None, help='Comma-separated list of segments to exclude')

    # DKIM controls
    parser.add_argument('--dkim-private-key', type=str, default=None, help='Path to DKIM private key (PEM)')
    parser.add_argument('--dkim-selector', type=str, default=None, help='DKIM selector (e.g., default)')
    parser.add_argument('--dkim-domain', type=str, default=None, help='DKIM domain (e.g., example.com)')

    args = parser.parse_args()

    logging.info(f"Current working directory: {os.getcwd()}")
    logging.info(f"Current date and time: {datetime.now().strftime('%I:%M %p %Z, %A, %B %d, %Y')}")

    sender_email, username, password = load_environment(args.env)

    smtp_server = 'smtp.gmail.com'
    smtp_port = 587

    csv_list = get_csv_list(args.env)
    if not csv_list:
        logging.error(f"No CSV files defined for environment: {args.env}")
        sys.exit(1)

    # Build environment-specific subjects/templates/attachments
    subjects, html_templates, text_templates, attachments_list = [], [], [], []
    for csv in csv_list:
        if args.env in ('pension', 'governance'):
            subject = "Schools Are Ditching Spreadsheets for This Powerful New Platform"
            html_template = load_email_template("email-templates/to-send.html")
            text_template = load_email_template("email-templates/to-send.txt")
            attachments = [
                "assets/may-19/Ascent Institute - May & June programs.pdf",
                "assets/may-19/Ascent Institute Calendar - 2025.pdf",
                "assets/may-19/company profile.pdf",
                "assets/Men's Breakfast Poster.jpg",
                "assets/Enhancing Productivity for office professionals workshop _16th - 20th June 2025.pdf",
                "assets/Nomination Form 16th to 20th June 2025 -Enhancing productivity for office professionals.pdf",
                "assets/2025 Governance Trainings.pdf",
            ]
        else:  # it
            subject = "REMINDER: August Professional Development Programs"
            html_template = load_email_template("email-templates/to-send.html")
            text_template = load_email_template("email-templates/to-send.txt")
            attachments = [
                "assets/August Combined/Fleet and Transport Training August 2025.pdf",
                "assets/August Combined/Modern Electronic Cash Management August 2025.pdf",
                "assets/Capetown ESG/Capetown Invitation 23rd August to 30th August 2025.pdf",
                "assets/August Combined/Strategic procurement excellence August 2025.pdf",
                "assets/Master Class Ex. Management/Ascent Approved 2025 Training Calendar.pdf",
            ]
        subjects.append(subject)
        html_templates.append(html_template)
        text_templates.append(text_template)
        attachments_list.append(attachments)

    # Confirm before sending
    if not confirm_campaign_details(
        csv_list, subjects, html_templates, text_templates, attachments_list,
        smtp_server, smtp_port, sender_email, args.resume,
        env_name=args.env
    ):
        logging.warning("Exiting due to user cancellation or validation failure")
        sys.exit(1)

    try:
        for csv_index, csv in enumerate(csv_list):
            logging.info(f"Processing CSV {csv_index + 1}/{len(csv_list)}: {csv}")
            logging.info(f"{args.env.capitalize()} environment setup complete for {csv}. Attachments: {', '.join(attachments_list[csv_index])}")

            include_segments = args.include_segments.split(',') if args.include_segments else None
            exclude_segments = args.exclude_segments.split(',') if args.exclude_segments else None

            results, sender = email_sender(
                subject=subjects[csv_index],
                files=attachments_list[csv_index],
                custom_html_template=html_templates[csv_index],
                custom_text_template=text_templates[csv_index],
                smtp_server=smtp_server,
                smtp_port=smtp_port,
                username=username,
                password=password,
                sender_email=sender_email,
                csv_file=csv,
                resume_from=args.resume,
                segment_col=args.segment_col,
                include_segments=include_segments,
                exclude_segments=exclude_segments,
                use_jinja=not args.no_jinja,
                jinja_strict=args.jinja_strict,
                dkim_private_key=args.dkim_private_key,
                dkim_selector=args.dkim_selector,
                dkim_domain=args.dkim_domain,
            )

            if results:
                logging.info(f"Email campaign summary for {csv}: {results}")
                print(f"Email campaign summary for {csv}: {results}")
            else:
                logging.error(f"Email campaign failed to complete for {csv}")
                print(f"Email campaign failed to complete for {csv}")

            if args.env == 'it' and csv.endswith("test.csv") and csv_index < len(csv_list) - 1:
                logging.info("Pausing after test.csv to review emails")
                print("\nPausing after test.csv to review emails.")
                remaining_csvs = csv_list[csv_index + 1:]
                remaining_subjects = subjects[csv_index + 1:]
                remaining_html_templates = html_templates[csv_index + 1:]
                remaining_text_templates = text_templates[csv_index + 1:]
                remaining_attachments = attachments_list[csv_index + 1:]
                if not confirm_campaign_details(
                    remaining_csvs,
                    remaining_subjects,
                    remaining_html_templates,
                    remaining_text_templates,
                    remaining_attachments,
                    smtp_server,
                    smtp_port,
                    sender_email,
                    0,
                    env_name=args.env,
                    is_post_test=True,
                ):
                    logging.warning("Exiting after test.csv due to user cancellation")
                    sys.exit(1)

            args.resume = 0
            logging.info(f"Completed processing {csv}. Moving to next CSV if available.")

    except KeyboardInterrupt:
        logging.warning("Script interrupted by user (Ctrl+C). Terminating process.")
        print("\nScript interrupted by user (Ctrl+C). Terminating process.")
        if 'sender' in locals():
            sender.disconnect()
        sys.exit(1)
    except Exception as e:
        logging.error(f"Unexpected error during CSV processing: {str(e)}")
        print(f"ERROR: Unexpected error during CSV processing: {str(e)}")
        if 'sender' in locals():
            sender.disconnect()
        sys.exit(1)

    logging.info("All CSVs processed or skipped.")
    print("All CSVs processed or skipped.")

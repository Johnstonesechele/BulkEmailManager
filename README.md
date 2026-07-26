# Bulk Email Manager

A full-featured desktop GUI application for managing contacts, email/SMS templates, and running bulk email campaigns with DKIM support. Built with PySide6 (Qt).

## Features

- **Contact Management** - Load, merge, deduplicate, and filter contacts from CSV files
- **Email Templates** - HTML and plain text templates with Jinja2 variable personalization
- **Bulk Email Campaigns** - Send personalized emails with pacing, retries, and Gmail block detection
- **DKIM Signing** - Optional DKIM authentication for improved deliverability
- **Attachment Support** - Attach up to 10 files per campaign
- **Segment Filtering** - Include/exclude contacts by segment tags
- **Bulk SMS** - Send SMS via GSM modem (AT commands)
- **Database-Backed Contacts & Templates** - SQLite storage for contacts, SMS templates, email templates, and survey data
- **Surveys** - Create surveys with text, multiple-choice, and checkbox questions
- **Analytics** - Track email/SMS campaign statistics
- **Dark Theme** - Dark Blue & Dark Gold UI

## Quick Start (Pre-built Installer)

Download the latest release from the [Releases](https://github.com/your-username/bulk-email-manager/releases) page and run the installer.

## Install from Source

### Prerequisites

- Python 3.10 or later
- Windows 10/11 (for the GUI), or Linux/macOS with a display server

### Setup

```bash
git clone https://github.com/your-username/bulk-email-manager.git
cd bulk-email-manager
pip install -r requirements.txt
```

### Configuration

Copy the example environment file and fill in your SMTP credentials:

```bash
cp .env.example .env.it
```

Edit `.env.it` (or create `your own environment file`) with your email provider details:

```
EMAIL_USERNAME=you@example.com
EMAIL_PASSWORD=your-app-password
SENDER_EMAIL=you@example.com
SENDER_NAME=Your Name
SMTP_SERVER=smtp.gmail.com
SMTP_PORT=587
```

For Gmail, use an [App Password](https://support.google.com/accounts/answer/185833) instead of your regular password.

### Run the App

```bash
python bulk_email.py
```

## Building the Installer

### Option 1: Build Everything (Recommended)

Run the build script from the `installer/` directory:

```bash
cd installer
.\build.ps1
```

This will:
1. Build the standalone EXE with PyInstaller
2. Create a portable ZIP in `installer/output/`
3. Attempt to build an MSI installer with cx_Freeze
4. Build a professional EXE installer if Inno Setup is installed

### Option 2: Portable App Only

```bash
python -m PyInstaller BulkEmail.spec --noconfirm
```

The standalone app will be in `dist/BulkEmailManager/`. Zip it and distribute.

### Option 3: MSI Installer

```bash
python setup_cx.py bdist_msi
```

Creates an MSI installer in `dist/`.

### Option 4: Professional EXE Installer (Inno Setup)

1. Download and install [Inno Setup](https://jrsoftware.org/isinfo.php) (free)
2. Run `python -m PyInstaller BulkEmail.spec --noconfirm` first
3. Open `installer/setup.iss` in Inno Setup
4. Click **Build > Compile**
5. The installer will be in `installer/output/`

### Build Outputs

| Output | Location | Description |
|--------|----------|-------------|
| Standalone EXE | `dist/BulkEmailManager/` | Run directly, no install needed |
| Portable ZIP | `installer/output/` | Zip of the standalone app |
| MSI Installer | `dist/*.msi` | Windows MSI installer |
| EXE Installer | `installer/output/*-Setup.exe` | Professional installer with shortcuts |

## Usage

### GUI Application

```bash
python bulk_email.py
```

### CLI (backend.py)

```bash
# Send to IT segment
python backend.py -e it

# Send to pension segment
python backend.py -e pension

# Resume a paused campaign
python backend.py -e it --resume 150

# With segmentation
python backend.py -e it --segment-col Segment --include-segments "Banks,Hospitals"

# With DKIM
python backend.py -e it --dkim-private-key key.pem --dkim-selector default --dkim-domain example.com
```

## CSV Format

Contact CSV files must contain an `Emails` column. Optional columns:

| Column | Description |
|--------|-------------|
| `Emails` | **Required** - Recipient email address |
| `FirstName` | First name for personalization |
| `LastName` | Last name for personalization |
| `Segment` | Segment tag for filtering |
| `cc` | CC addresses (comma-separated) |
| `bcc` | BCC addresses (comma-separated) |

## Template Variables

Use Jinja2 syntax in HTML/text templates:

```html
<p>Hello {{ FirstName }} {{ LastName }},</p>
<p>Your segment: {{ Segment }}</p>
```

Or simple `{{VariableName}}` placeholders (Jinja2 mode is default).

## Project Structure

```
bulk-email/
├── bulk_email.py          # Main GUI application (PySide6)
├── backend.py             # CLI email sender with Jinja2 + DKIM
├── version2.py            # Alternate GUI version with GSM SMS
├── sms_db.py              # SQLite database schema & init
├── contacts_db.py         # Contact CRUD operations
├── email_db.py            # Email template & campaign DB ops
├── sms_campaign_db.py     # SMS campaign & log DB ops
├── templates_db.py        # SMS template DB ops
├── survey_db.py           # Survey DB ops
├── gsm_sender.py          # GSM modem SMS sender
├── BulkEmail.spec         # PyInstaller build spec
├── setup_cx.py            # cx_Freeze MSI build config
├── file_version_info.txt  # Windows EXE version info
├── installer/
│   ├── build.bat          # Batch build script
│   ├── build.ps1          # PowerShell build script
│   └── setup.iss          # Inno Setup installer script
├── email-templates/       # HTML and text email templates
├── assets/                # PDF/image attachments (user-provided)
├── emails/                # Contact CSV files (user-provided)
├── data/                  # Sample data
├── requirements.txt       # Python dependencies
├── .env.example           # Environment variable template
└── CHANGELOG.md           # Version history
```

## License

MIT

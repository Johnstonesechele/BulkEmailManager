"""
cx_Freeze setup for building Bulk Email Manager as MSI installer.
Usage: python setup_cx.py build_msi
"""
import sys
import os
from cx_Freeze import setup, Executable

BASE_DIR = os.path.dirname(os.path.abspath(__file__))

# Dependencies are detected automatically, but include these explicitly
build_exe_options = {
    "packages": [
        "os", "sys", "re", "csv", "json", "time", "random", "shutil",
        "logging", "smtplib", "threading", "email", "sqlite3",
        "pandas", "dotenv", "jinja2", "email_validator",
        "PySide6", "PySide6.QtCore", "PySide6.QtGui", "PySide6.QtWidgets",
    ],
    "include_files": [
        ("email-templates", "email-templates"),
        (".env.example", ".env.example"),
    ],
    "excludes": [
        "tkinter", "matplotlib", "numpy.testing",
        "pytest", "unittest", "xmlrpc",
    ],
    "optimize": 0,
}

# MSI options
bdist_msi_options = {
    "upgrade_code": "{A1B2C3D4-E5F6-7890-ABCD-EF1234567890}",
    "add_to_path": False,
    "initial_target_dir": r"[ProgramFilesFolder]\BulkEmailManager",
    "install_icon": None,
    "uninstall_icon": None,
    "title": "Bulk Email Manager",
    "author": "Bulk Email Manager",
    "manufacturer": "Bulk Email Manager",
    "version": "2.0.0",
    "compressed": True,
    "install_mode": "perMachine",
}

setup(
    name="Bulk Email Manager",
    version="2.0.0",
    description="Full-featured bulk email campaign manager with SMS and survey support",
    author="Bulk Email Manager",
    options={
        "build_exe": build_exe_options,
        "bdist_msi": bdist_msi_options,
    },
    executables=[
        Executable(
            "bulk_email.py",
            base="Win32GUI",
            target_name="BulkEmailManager.exe",
            shortcut_name="Bulk Email Manager",
            shortcut_dir="DesktopFolder",
        )
    ],
)

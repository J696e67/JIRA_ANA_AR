"""
config.py
All configuration: SMTP, file paths, hourly rate, defaults.
Values are read from environment variables with sensible defaults.
"""
import os

# SMTP settings
SMTP_HOST = os.environ.get("SMTP_HOST", "smtp.gmail.com")
SMTP_PORT = int(os.environ.get("SMTP_PORT", "587"))

# Default email addresses
DEFAULT_FROM_ADDR = os.environ.get("DEFAULT_FROM_ADDR", "nicejingy@gmail.com")
DEFAULT_TO_ADDR = os.environ.get("DEFAULT_TO_ADDR", "nicejingy@gmail.com")
DEFAULT_CC_ADDR = os.environ.get("DEFAULT_CC_ADDR", "jing.yang@mssm.edu")

# Invoice settings
HOURLY_RATE = float(os.environ.get("HOURLY_RATE", "177"))

# Upload limits
MAX_UPLOAD_SIZE_MB = int(os.environ.get("MAX_UPLOAD_SIZE_MB", "16"))

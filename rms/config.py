import os
from pathlib import Path
from dotenv import load_dotenv

load_dotenv(Path(__file__).with_name(".env"))

BASE_DIR = Path(__file__).parent
INSTANCE = BASE_DIR / "instance"
INSTANCE.mkdir(exist_ok=True)

class Config:
    SECRET_KEY  = os.getenv("SECRET_KEY", "dev-secret")
    SQLALCHEMY_DATABASE_URI = os.getenv(
        "DATABASE_URL",
        f"sqlite:///{INSTANCE/'rms.db'}"
    )
    SQLALCHEMY_TRACK_MODIFICATIONS = False

    # Uploads
    UPLOAD_FOLDER      = INSTANCE / "uploads"
    UPLOAD_FOLDER.mkdir(exist_ok=True)
    MAX_CONTENT_LENGTH = 20 * 1024 * 1024
    ALLOWED_EXTENSIONS = {"png","jpg","jpeg","pdf"}

    # SMTP mail
    SMTP_SERVER  = os.getenv("SMTP_SERVER", "smtp.mailgun.org")
    SMTP_PORT    = int(os.getenv("SMTP_PORT", "587").split()[0])
    SMTP_USER    = os.getenv("SMTP_USER", "")
    SMTP_PASS    = os.getenv("SMTP_PASS", "")
    SMTP_USE_TLS = os.getenv("SMTP_USE_TLS", "true").lower() not in ("0","false")
    MAIL_FROM    = os.getenv("MAIL_FROM", "")

    # Approver emails
    APPROVERS = {
      "Sales Return":      os.getenv("APPROVER_SALES","sales@tworiversmeats.com"),
      "Vendor Return":     os.getenv("APPROVER_VENDOR","vendor@tworiversmeats.com"),
      "Production Return": os.getenv("APPROVER_PROD","prod@tworiversmeats.com")
    }

    SITE_VERSION = "1.1.0"
    TZ_NAME      = os.getenv("TZ_NAME","America/Los_Angeles")

class DevConfig(Config):
    DEBUG = True

class ProdConfig(Config):
    DEBUG = False

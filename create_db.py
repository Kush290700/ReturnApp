#!/usr/bin/env python
import os
import time
from io import BytesIO
import psycopg2
from psycopg2 import sql, OperationalError
import dotenv
from sqlalchemy.engine import make_url

# ── 1) grab & parse DATABASE_URL via SQLAlchemy ─────────────────────────────
raw_url = "postgresql+psycopg2://postgres:Kush%40trsm@127.0.0.1:5432/rms_db"
if not raw_url:
    raise RuntimeError("DATABASE_URL must be set")

url = make_url(raw_url)
user      = url.username
password  = url.password
host      = url.host or "127.0.0.1"
port      = url.port or 5432
target_db = url.database

# ── 2) choose a maintenance database (must already exist) ────────────────────
maint_db = os.getenv("PG_MAINT_DB", "postgres")

# ── 3) wait (up to 30s) for Postgres on maint_db to come up ─────────────────
start = time.time()
while True:
    try:
        conn = psycopg2.connect(
            dbname   = maint_db,
            user     = user,
            password = password,
            host     = host,
            port     = port
        )
        break
    except OperationalError:
        if time.time() - start > 30:
            raise RuntimeError(f"Cannot connect to Postgres at {host}:{port}")
        print(f"Waiting for Postgres at {host}:{port}…")
        time.sleep(2)

conn.autocommit = True
cur = conn.cursor()

# ── 4) create target database if missing ───────────────────────────────────
cur.execute(
    "SELECT 1 FROM pg_database WHERE datname = %s;",
    (target_db,)
)
if not cur.fetchone():
    cur.execute(sql.SQL("CREATE DATABASE {}").format(
        sql.Identifier(target_db)
    ))
    print(f"Created database {target_db!r}")
else:
    print(f"Database {target_db!r} already exists")

cur.close()
conn.close()

# ── 5) run Alembic migrations & seed users ───────────────────────────────────
os.environ["DATABASE_URL"] = raw_url

# locate alembic.ini
here      = os.path.abspath(os.path.dirname(__file__))
ini_root  = os.path.join(here, "alembic.ini")
ini_mig   = os.path.join(here, "migrations", "alembic.ini")
if     os.path.exists(ini_root):   alembic_ini = ini_root
elif   os.path.exists(ini_mig):    alembic_ini = ini_mig
else:
    raise FileNotFoundError(f"Could not find alembic.ini in {ini_root} or {ini_mig}")

from .run                  import create_app
from rms.models           import db, User
from werkzeug.security    import generate_password_hash
from alembic.config       import Config
from alembic              import command

app = create_app()
with app.app_context():
    cfg = Config(alembic_ini)
    cfg.set_main_option("script_location", os.path.join(here, "migrations"))

    # ── Escape % so configparser won’t choke on '%40', etc. ───────────────
    url_escaped = raw_url.replace("%", "%%")
    cfg.set_main_option("sqlalchemy.url", url_escaped)

    print("→ Upgrading to head…")
    command.upgrade(cfg, "head")

    # seed a few default users if they don't exist
    default_users = [
        ("kush@tworiversmeats.com", "adminpass",  "admin",     True),
        ("bob@tworiversmeats.com",  "warehouse1", "warehouse", True),
        ("test@tworiversmeats.com", "testpass",   "sales",     True),
    ]
    for email, pw, role, active in default_users:
        if not User.query.filter_by(username=email).first():
            u = User(username=email, role=role, is_active=active)
            if hasattr(u, "set_password"):
                u.set_password(pw)
            else:
                u.password = generate_password_hash(pw)
            db.session.add(u)

    db.session.commit()
    print("✓ Migrations applied and default users seeded.")

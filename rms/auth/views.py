# rms/auth/views.py

import time
import random, string, re
from email_validator import validate_email, EmailNotValidError
from flask import (
    Blueprint, render_template, request, redirect,
    url_for, flash, session, current_app
)
from flask_login import login_user, logout_user, current_user
from ..mailer import smtp_send
from ..extensions import db
from ..models import User

auth_bp = Blueprint(
    "auth", __name__,
    template_folder="../templates",
    url_prefix="/auth",
)

# only allow our company emails
_DOMAIN = re.compile(r".+@tworiversmeats\.com$", re.I)

def _gen_code(n=6):
    return "".join(random.choices(string.digits, k=n))

def _send_otp(email, code):
    subject = "ReturnApp Registration Code"
    body    = render_template(
        "emails/otp.txt",
        code=code,
        company=current_app.config.get("COMPANY_NAME", "ReturnApp")
    )
    return smtp_send(email, subject, body)

# ──────────────────────────────────────────────────────────────────────────────
@auth_bp.route("/login", methods=["GET", "POST"])
def login():
    if current_user.is_authenticated:
        return redirect(url_for("main.index"))

    if request.method == "POST":
        email = request.form["username"].lower().strip()
        pwd   = request.form["password"]
        u     = User.query.filter_by(username=email).first()

        if u and u.is_active and u.check_password(pwd):
            login_user(u)
            flash("Logged in successfully", "success")
            return redirect(url_for("main.index"))

        flash("Invalid credentials or account pending activation", "danger")

    return render_template("login.html")


# ──────────────────────────────────────────────────────────────────────────────
@auth_bp.route("/register", methods=["GET", "POST"])
def register():
    if current_user.is_authenticated:
        return redirect(url_for("main.index"))

    if request.method == "POST":
        email = request.form["email"].lower().strip()
        # basic syntax + domain check
        try:
            validate_email(email)
            assert _DOMAIN.fullmatch(email)
        except (EmailNotValidError, AssertionError):
            flash("Use your @tworiversmeats.com email address", "warning")
            return render_template("register.html")

        # generate & mail OTP
        otp = _gen_code(current_app.config.get("OTP_LENGTH", 6))
        session["reg_email"]    = email
        session["reg_otp"]      = otp
        session["reg_otp_ts"]   = int(time.time())
        session["reg_attempts"] = 0

        if not _send_otp(email, otp):
            flash("Could not send verification code; try again later", "danger")
            session.pop("reg_email", None)
            return render_template("register.html")

        flash("OTP sent! Check your inbox.", "info")
        return redirect(url_for("auth.verify"))

    return render_template("register.html")


# ──────────────────────────────────────────────────────────────────────────────
@auth_bp.route("/register/verify", methods=["GET", "POST"])
def verify():
    email = session.get("reg_email")
    if not email:
        return redirect(url_for("auth.register"))

    now = int(time.time())
    ts  = session.get("reg_otp_ts", 0)
    window = current_app.config.get("OTP_EXPIRATION", 600)
    attempts = session.get("reg_attempts", 0)
    max_attempts = current_app.config.get("OTP_MAX_ATTEMPTS", 5)

    # OTP expired?
    if now - ts > window:
        flash("Verification code has expired; please register again.", "warning")
        for k in ("reg_email","reg_otp","reg_otp_ts","reg_attempts"):
            session.pop(k, None)
        return redirect(url_for("auth.register"))

    if request.method == "POST":
        entered = request.form["otp"].strip()
        pwd  = request.form["password"]
        pwd2 = request.form["password2"]

        # too many tries?
        if attempts >= max_attempts:
            flash("Too many failed attempts; start over.", "danger")
            return redirect(url_for("auth.register"))

        # check OTP
        if entered != session.get("reg_otp"):
            session["reg_attempts"] = attempts + 1
            flash(f"Wrong code ({attempts+1}/{max_attempts})", "danger")

        # check password
        elif pwd != pwd2 or len(pwd) < 8:
            flash("Passwords must match and be at least 8 characters", "warning")

        else:
            # create or update user
            u = User.query.filter_by(username=email).first()
            if not u:
                u = User(username=email,
                         name=email.split("@")[0].title(),
                         role=current_app.config.get("DEFAULT_ROLE","sales"),
                         is_active=False)
                db.session.add(u)

            u.set_password(pwd)
            # remains inactive until admin flips is_active
            db.session.commit()

            # clear session
            for k in ("reg_email","reg_otp","reg_otp_ts","reg_attempts"):
                session.pop(k, None)

            # notify admins
            admin_list = current_app.config.get("ADMIN_EMAILS", [])
            for admin in admin_list:
                smtp_send(
                    admin,
                    f"New user registration: {u.username}",
                    render_template("emails/new_user_admin.txt", user=u)
                )

            flash("Thanks! Your account is pending admin approval.", "success")
            return redirect(url_for("auth.login"))

    return render_template("register_verify.html", email=email,
                                         expires_in=window - (now - ts))


# ──────────────────────────────────────────────────────────────────────────────
@auth_bp.route("/logout")
def logout():
    logout_user()
    flash("Logged out", "info")
    return redirect(url_for("auth.login"))

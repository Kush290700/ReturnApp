# rms/admin/views.py

from flask import Blueprint, render_template, redirect, url_for, flash, abort, request
from flask_login import login_required, current_user

from ..extensions import db
from ..models     import User

admin_bp = Blueprint("admin", __name__,
                     template_folder="../templates",
                     url_prefix="/admin")

@admin_bp.before_request
@login_required
def require_admin():
    if current_user.role != "admin":
        abort(403)

@admin_bp.route("/")
def index():
    return redirect(url_for("admin.manage_users"))

@admin_bp.route("/users")
def manage_users():
    users   = User.query.order_by(User.joined_at.desc()).all()
    pending = User.query.filter_by(is_active=False).count()
    return render_template("admin_users.html",
                           users=users,
                           pending=pending)

@admin_bp.route("/users/<int:id>/toggle", methods=["POST"])
def toggle_user(id: int):
    u = User.query.get_or_404(id)
    u.is_active = not u.is_active
    db.session.commit()
    flash(f"{u.username} {'activated' if u.is_active else 'deactivated'}","info")
    return redirect(url_for("admin.manage_users"))

@admin_bp.route("/users/<int:id>/edit", methods=["GET", "POST"])
def edit_user(id: int):
    u = User.query.get_or_404(id)

    if request.method == "POST":
        form = request.form

        # -- Email (username)
        new_email = form["username"].strip().lower()
        if new_email != u.username:
            if User.query.filter_by(username=new_email).first():
                flash(f"⚠️ Email {new_email!r} is already in use.", "danger")
                return render_template("admin_user_edit.html", u=u)
            u.username = new_email

        # -- Name & Role
        u.name = form["name"].strip()
        u.role = form["role"]

        # -- Password (only if provided)
        pw = form.get("password", "").strip()
        if pw:
            if len(pw) < 8:
                flash("⚠️ Password must be at least 8 characters.", "warning")
                return render_template("admin_user_edit.html", u=u)
            u.set_password(pw)

        db.session.commit()
        flash("User updated","success")
        return redirect(url_for("admin.manage_users"))

    return render_template("admin_user_edit.html", u=u)

from flask import Blueprint, redirect, url_for
from flask_login import current_user

main_bp = Blueprint('main', __name__)

@main_bp.route('/')
def index():
    # bounce anonymously to login, otherwise to returns list
    if current_user.is_authenticated:
        return redirect(url_for('returns.list_returns'))
    return redirect(url_for('auth.login'))

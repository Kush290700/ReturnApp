# rms/cli.py

import click
from flask.cli import with_appcontext
from .extensions import db
from .models     import User

@click.command("create-admin")
@with_appcontext
def create_admin():
    """
    Create a default admin user if it doesn't already exist.
    """
    email = "admin@tworiversmeats.com"
    pw    = "admin123"

    # look up by username (which is your email column)
    if User.query.filter_by(username=email).first():
        click.echo(f"👤 Admin user {email!r} already exists.")
        return

    # build + persist
    u = User(
        username=email,
        name="Administrator",
        role="admin",
        is_active=True
    )
    u.set_password(pw)

    db.session.add(u)
    db.session.commit()

    click.echo(f"✅ Created admin user {email!r} with password {pw!r}")

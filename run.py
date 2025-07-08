# run.py

import click
from flask import Flask
from rms.models import User
from rms.extensions import db
from rms import create_app
import dotenv


dotenv.load_dotenv()   
app = create_app()

@app.cli.command("create-admin")
@click.argument("email")
@click.argument("password")
def create_admin(email, password):
    """
    Create a new admin user.
    Example: flask create-admin admin@tworiversmeats.com admin123
    """
    if User.query.filter_by(username=email).first():
        click.echo(f"⚠️  User {email!r} already exists.")
        return

    u = User(
        username=email,
        role="admin",
        is_active=True
    )
    # if you have the set_password helper:
    u.set_password(password)
    db.session.add(u)
    db.session.commit()

    click.echo(f"✅ Admin {email!r} created.")

@app.cli.command("create-user")
@click.argument("email")
@click.argument("password")
@click.argument("role", default="sales", required=False)
def create_user(email, password, role):
    """
    Create a new user.
    Example: flask create-user alice@tworiversmeats.com secretpass sales
    If you omit ROLE it defaults to 'sales'.
    """
    if User.query.filter_by(username=email).first():
        click.echo(f"⚠️  User {email!r} already exists.")
        return

    u = User(
        username=email,
        role=role.lower(),
        is_active=True
    )
    u.set_password(password)
    db.session.add(u)
    db.session.commit()

    click.echo(f"✅ {role.title()} user {email!r} created.")
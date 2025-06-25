# rms/__init__.py

from datetime import datetime
from flask import Flask
from flask_login import current_user

from .extensions      import db, migrate, login_manager
from .auth.views      import auth_bp
from .returns.views   import returns_bp
from .analytics.views import analytics_bp
from .admin.views     import admin_bp
from .main.views      import main_bp
from .models          import Return
from .cli             import create_admin  # your custom CLI

def create_app(config="rms.config.DevConfig"):
    app = Flask(__name__, instance_relative_config=False)
    app.config.from_object(config)

    # initialize extensions
    db.init_app(app)
    migrate.init_app(app, db)
    login_manager.init_app(app)
    login_manager.login_view = "auth.login"

    # register blueprints
    app.register_blueprint(auth_bp,      url_prefix="/auth")
    app.register_blueprint(returns_bp,   url_prefix="/returns")
    app.register_blueprint(analytics_bp, url_prefix="/analytics")
    app.register_blueprint(admin_bp,     url_prefix="/admin")
    app.register_blueprint(main_bp)  # handles root "/"

    # register your custom CLI command
    app.cli.add_command(create_admin)

    # inject globals into every template
    @app.context_processor
    def inject_globals():
        pending = 0
        if current_user.is_authenticated and current_user.role in ("warehouse","admin"):
            pending = Return.query.filter_by(status="Pending").count()
        return dict(now=datetime.utcnow, pending=pending, config=app.config)

    return app

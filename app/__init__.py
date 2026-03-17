from flask import Flask, redirect, url_for
from flask_login import LoginManager
from app.config import Config
from app.database import init_engine, init_db, close_session


login_manager = LoginManager()


def create_app():
    app = Flask(__name__)
    app.config.from_object(Config)

    # Database
    init_engine(app.config["DATABASE_URL"])
    with app.app_context():
        init_db()

    # Session cleanup
    app.teardown_appcontext(close_session)

    # Auth
    login_manager.init_app(app)
    login_manager.login_view = "auth.login"
    login_manager.login_message = "Please log in to access this page."

    from app.auth import User, load_user as _load_user
    login_manager.user_loader(_load_user)

    # Blueprints
    from app.routes.auth import bp as auth_bp
    from app.routes.dashboard import bp as dash_bp
    from app.routes.catalog import bp as catalog_bp
    from app.routes.containers import bp as containers_bp
    from app.routes.sales import bp as sales_bp
    from app.routes.reports import bp as reports_bp

    app.register_blueprint(auth_bp)
    app.register_blueprint(dash_bp)
    app.register_blueprint(catalog_bp)
    app.register_blueprint(containers_bp)
    app.register_blueprint(sales_bp)
    app.register_blueprint(reports_bp)

    @app.route("/")
    def index():
        return redirect(url_for("dashboard.index"))

    @app.route("/health")
    def health():
        return {"status": "ok"}

    return app

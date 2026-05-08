import os
import logging
from flask import Flask, jsonify
from flask_cors import CORS
from dotenv import load_dotenv

load_dotenv()

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
)
logger = logging.getLogger(__name__)


def create_app() -> Flask:
    app = Flask(__name__)
    CORS(app, resources={r"/api/*": {"origins": "*"}})

    from .extensions import limiter
    limiter.init_app(app)

    @app.errorhandler(429)
    def ratelimit_handler(e):
        return jsonify({"error": "Rate limit exceeded. Please slow down.", "retry_after": str(e.description)}), 429

    from .database.schema import init_db
    from .database.seed_data import seed_database

    init_db()
    seed_database()

    from .api.invoices import invoices_bp
    from .api.memory import memory_bp
    from .api.observability import observability_bp
    from .api.notifications import notifications_bp

    app.register_blueprint(invoices_bp)
    app.register_blueprint(memory_bp)
    app.register_blueprint(observability_bp)
    app.register_blueprint(notifications_bp)

    from .observability.monitor import start_monitor
    start_monitor(interval=60)

    @app.route("/api/health")
    def health():
        return {"status": "ok", "service": "InvoiceGuard"}

    logger.info("InvoiceGuard API server initialized.")
    return app


if __name__ == "__main__":
    app = create_app()
    port = int(os.environ.get("PORT", 5000))
    app.run(host="0.0.0.0", port=port, debug=os.environ.get("FLASK_DEBUG", "false").lower() == "true")

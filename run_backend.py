"""Entry point for the InvoiceGuard backend server."""
import sys
import os

sys.path.insert(0, os.path.dirname(__file__))

from invoice_processor.backend.main import create_app

if __name__ == "__main__":
    import os
    app = create_app()
    port = int(os.environ.get("PORT", 5000))
    debug = os.environ.get("FLASK_DEBUG", "false").lower() == "true"
    print(f"InvoiceGuard backend starting on http://localhost:{port}")
    app.run(host="0.0.0.0", port=port, debug=debug, use_reloader=False)

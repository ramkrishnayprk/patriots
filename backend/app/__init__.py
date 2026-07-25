import logging
import os

from flask import Flask, jsonify

from app.api.routes import api


def create_app() -> Flask:
    app = Flask(__name__)
    app.config["JSON_SORT_KEYS"] = False

    logging.basicConfig(
        level=os.getenv("LOG_LEVEL", "INFO").upper(),
        format="%(asctime)s | %(levelname)s | %(name)s | %(message)s",
    )

    app.register_blueprint(api)

    @app.errorhandler(404)
    def not_found(_error):
        return jsonify({"error": {"code": "not_found", "message": "Resource not found."}}), 404

    @app.errorhandler(405)
    def method_not_allowed(_error):
        return (
            jsonify(
                {
                    "error": {
                        "code": "method_not_allowed",
                        "message": "Method not allowed.",
                    }
                }
            ),
            405,
        )

    return app

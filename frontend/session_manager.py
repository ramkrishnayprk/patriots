from flask import Flask, request, jsonify
import json
import os
from datetime import datetime
from pathlib import Path

app = Flask(__name__)

class SessionManager:
    def __init__(self, storage_dir="./sessions"):
        self.storage_dir = Path(storage_dir)
        # Create the storage folder if it does not exist
        self.storage_dir.mkdir(parents=True, exist_ok=True)

    def _get_file_path(self, session_id: str) -> Path:
        return self.storage_dir / f"{session_id}.json"

    def create_session(self, session_id: str, system_prompt: str = "You are a helpful assistant.") -> dict:
        file_path = self._get_file_path(session_id)
        now_iso = datetime.utcnow().isoformat() + "Z"

        session_data = {
            "sessionId": session_id,
            "createdAt": now_iso,
            "updatedAt": now_iso,
            "messages": [
                {"role": "system", "content": system_prompt}
            ]
        }

        # Write the fresh session structure to a local JSON file
        with open(file_path, "w", encoding="utf-8") as f:
            json.dump(session_data, f, indent=2)

        return session_data

    def get_or_create_session(self, session_id: str, default_system_prompt: str = "You are a helpful assistant.") -> dict:
        file_path = self._get_file_path(session_id)

        if file_path.exists():
            with open(file_path, "r", encoding="utf-8") as f:
                return json.load(f)

        return self.create_session(session_id, default_system_prompt)

    def add_message(self, session_id: str, role: str, content: str) -> dict:
        session = self.get_or_create_session(session_id)

        # Append the new message to the history array
        session["messages"].append({"role": role, "content": content})
        session["updatedAt"] = datetime.utcnow().isoformat() + "Z"

        file_path = self._get_file_path(session_id)
        with open(file_path, "w", encoding="utf-8") as f:
            json.dump(session, f, indent=2)

        return session

session_manager = SessionManager()

@app.route("/create_session", methods=["POST"])
def create_session():
    data = request.get_json()
    session_id = data.get("sessionId")
    system_prompt = data.get("systemPrompt", "You are a helpful assistant.")

    if not session_id:
        return jsonify({"error": "sessionId is required"}), 400

    session_data = session_manager.create_session(session_id, system_prompt)
    return jsonify(session_data), 201

@app.route("/get_session/<session_id>", methods=["GET"])
def get_session(session_id):
    try:
        session_data = session_manager.get_or_create_session(session_id)
        return jsonify(session_data), 200
    except Exception as e:
        return jsonify({"error": str(e)}), 500

@app.route("/update_session/<session_id>", methods=["PUT"])
def update_session(session_id):
    data = request.get_json()
    role = data.get("role")
    content = data.get("content")

    if not role or not content:
        return jsonify({"error": "Both 'role' and 'content' are required"}), 400

    try:
        updated_session = session_manager.add_message(session_id, role, content)
        return jsonify(updated_session), 200
    except Exception as e:
        return jsonify({"error": str(e)}), 500

if __name__ == "__main__":
    app.run(debug=True)
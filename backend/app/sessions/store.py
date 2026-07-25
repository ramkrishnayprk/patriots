import json
import os
from datetime import UTC, datetime
from pathlib import Path
from typing import Any
from uuid import UUID, uuid4


class InvalidSessionIdError(ValueError):
    """Raised when a session ID is not a canonical UUID."""


class SessionNotFoundError(FileNotFoundError):
    """Raised when a requested session does not exist."""


class SessionStorageError(OSError):
    """Raised when session data cannot be read or written."""


class JsonFileSessionStore:
    """Persist one JSON document per session in a local directory."""

    def __init__(self, directory: Path) -> None:
        self.directory = directory

    def create(self) -> dict[str, Any]:
        now = datetime.now(UTC).isoformat()
        session = {
            "id": str(uuid4()),
            "title": "New Session",
            "messages": [],
            "created_at": now,
            "updated_at": now,
        }
        self._write(session)
        return session

    def get(self, session_id: str) -> dict[str, Any]:
        normalized_id = self._normalize_id(session_id)
        path = self.directory / f"{normalized_id}.json"

        try:
            with path.open(encoding="utf-8") as file:
                session = json.load(file)
        except FileNotFoundError as exc:
            raise SessionNotFoundError("Session not found.") from exc
        except (OSError, json.JSONDecodeError) as exc:
            raise SessionStorageError("The session could not be read.") from exc

        if not isinstance(session, dict):
            raise SessionStorageError(f"Invalid session document: {path.name}")
        return session

    def append_message(self, session_id: str, role: str, content: str) -> dict[str, Any]:
        session = self.get(session_id)
        now = datetime.now(UTC).isoformat()
        session["messages"].append({"role": role, "content": content, "created_at": now})
        session["updated_at"] = now
        if role == "user" and len(session["messages"]) == 1:
            session["title"] = content.strip()[:60] or session["title"]
        self._write(session)
        return session

    def append_turn(
        self,
        session_id: str,
        *,
        user_content: str,
        assistant_content: str,
        assistant_extra: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        session = self.get(session_id)
        now = datetime.now(UTC).isoformat()

        if not session["messages"]:
            session["title"] = user_content.strip()[:60] or session["title"]

        assistant_message = {"role": "assistant", "content": assistant_content, "created_at": now}
        if assistant_extra:
            assistant_message.update(assistant_extra)

        session["messages"].append({"role": "user", "content": user_content, "created_at": now})
        session["messages"].append(assistant_message)
        session["updated_at"] = now
        self._write(session)
        return session

    def list_all(self) -> list[dict[str, Any]]:
        if not self.directory.exists():
            return []

        sessions: list[dict[str, Any]] = []
        try:
            paths = sorted(self.directory.glob("*.json"))
            for path in paths:
                with path.open(encoding="utf-8") as file:
                    session = json.load(file)
                if not isinstance(session, dict):
                    raise SessionStorageError(f"Invalid session document: {path.name}")
                sessions.append(session)
        except (OSError, json.JSONDecodeError) as exc:
            raise SessionStorageError("The sessions could not be read.") from exc

        return sorted(
            sessions,
            key=lambda session: str(session.get("created_at", "")),
            reverse=True,
        )

    def delete(self, session_id: str) -> None:
        normalized_id = self._normalize_id(session_id)
        path = self.directory / f"{normalized_id}.json"

        try:
            path.unlink()
        except FileNotFoundError as exc:
            raise SessionNotFoundError("Session not found.") from exc
        except OSError as exc:
            raise SessionStorageError("The session could not be deleted.") from exc

    def _write(self, session: dict[str, Any]) -> None:
        self._ensure_directory()
        destination = self.directory / f"{session['id']}.json"
        temporary = destination.with_suffix(".json.tmp")

        try:
            with temporary.open("w", encoding="utf-8") as file:
                json.dump(session, file, ensure_ascii=False, indent=2)
                file.write("\n")
                file.flush()
                os.fsync(file.fileno())
            temporary.replace(destination)
        except OSError as exc:
            temporary.unlink(missing_ok=True)
            raise SessionStorageError("The session could not be saved.") from exc

    def _ensure_directory(self) -> None:
        try:
            self.directory.mkdir(parents=True, exist_ok=True)
        except OSError as exc:
            raise SessionStorageError("The session directory could not be created.") from exc

    @staticmethod
    def _normalize_id(session_id: str) -> str:
        try:
            parsed = UUID(session_id)
        except (ValueError, AttributeError) as exc:
            raise InvalidSessionIdError("session_id must be a valid UUID.") from exc

        normalized = str(parsed)
        if session_id != normalized:
            raise InvalidSessionIdError("session_id must be a canonical UUID.")
        return normalized

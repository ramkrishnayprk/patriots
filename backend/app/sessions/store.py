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

    def create(
        self,
        *,
        title: str = "New Session",
        model_id: str = "",
        messages: list[dict[str, Any]] | None = None,
    ) -> dict[str, Any]:
        self._ensure_directory()

        now = datetime.now(UTC).isoformat()
        session = {
            "id": str(uuid4()),
            "title": title.strip() or "New Session",
            "model_id": model_id.strip(),
            "messages": [
                self._normalize_message(message, fallback_created_at=now)
                for message in (messages or [])
            ],
            "created_at": now,
            "updated_at": now,
        }
        self._write(session)

        return session

    def get(self, session_id: str) -> dict[str, Any]:
        return self._read(self._normalize_id(session_id))

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
            key=lambda session: str(session.get("updated_at", "")),
            reverse=True,
        )

    def append_messages(
        self,
        session_id: str,
        messages: list[dict[str, Any]],
    ) -> dict[str, Any]:
        if not messages:
            raise ValueError("messages cannot be empty.")

        normalized_id = self._normalize_id(session_id)
        session = self._read(normalized_id)
        now = datetime.now(UTC).isoformat()
        session_messages = session.get("messages")
        if not isinstance(session_messages, list):
            raise SessionStorageError("The session messages are invalid.")
        session_messages.extend(
            self._normalize_message(message, fallback_created_at=now)
            for message in messages
        )
        if session.get("title") in {"", "New Session", "New chat"}:
            first_user_message = next(
                (
                    message["content"]
                    for message in session_messages
                    if message.get("role") == "user"
                ),
                "",
            )
            if first_user_message:
                session["title"] = first_user_message[:60]
        session["updated_at"] = now
        self._write(session)
        return session

    def rename(self, session_id: str, title: str) -> dict[str, Any]:
        normalized_id = self._normalize_id(session_id)
        session = self._read(normalized_id)
        session["title"] = title.strip()
        session["updated_at"] = datetime.now(UTC).isoformat()
        self._write(session)
        return session

    def delete(self, session_id: str) -> None:
        normalized_id = self._normalize_id(session_id)
        path = self.directory / f"{normalized_id}.json"

        try:
            path.unlink()
        except FileNotFoundError as exc:
            raise SessionNotFoundError("Session not found.") from exc
        except OSError as exc:
            raise SessionStorageError("The session could not be deleted.") from exc

    def _ensure_directory(self) -> None:
        try:
            self.directory.mkdir(parents=True, exist_ok=True)
        except OSError as exc:
            raise SessionStorageError("The session directory could not be created.") from exc

    def _read(self, session_id: str) -> dict[str, Any]:
        path = self.directory / f"{session_id}.json"
        try:
            with path.open(encoding="utf-8") as file:
                session = json.load(file)
        except FileNotFoundError as exc:
            raise SessionNotFoundError("Session not found.") from exc
        except (OSError, json.JSONDecodeError) as exc:
            raise SessionStorageError("The session could not be read.") from exc
        if not isinstance(session, dict):
            raise SessionStorageError("The session document is invalid.")
        return session

    def _write(self, session: dict[str, Any]) -> None:
        destination = self.directory / f"{session['id']}.json"
        temporary = destination.with_suffix(f".json.{uuid4().hex}.tmp")
        try:
            with temporary.open("x", encoding="utf-8") as file:
                json.dump(session, file, ensure_ascii=False, indent=2)
                file.write("\n")
                file.flush()
                os.fsync(file.fileno())
            temporary.replace(destination)
        except OSError as exc:
            temporary.unlink(missing_ok=True)
            raise SessionStorageError("The session could not be saved.") from exc

    @staticmethod
    def _normalize_message(
        message: dict[str, Any],
        *,
        fallback_created_at: str,
    ) -> dict[str, Any]:
        if not isinstance(message, dict):
            raise ValueError("Each message must be a JSON object.")
        role = message.get("role")
        content = message.get("content")
        if role not in {"user", "assistant"}:
            raise ValueError("Message role must be user or assistant.")
        if not isinstance(content, str) or not content.strip():
            raise ValueError("Message content cannot be empty.")

        normalized = {
            "id": str(message.get("id") or uuid4()),
            "role": role,
            "content": content.strip(),
            "created_at": str(message.get("created_at") or fallback_created_at),
        }
        sources = message.get("sources")
        if isinstance(sources, list):
            normalized["sources"] = [
                source for source in sources if isinstance(source, dict)
            ]
        return normalized

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

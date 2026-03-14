from __future__ import annotations

import json
from copy import deepcopy
from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from http import HTTPStatus
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from typing import Any
from urllib.parse import urlparse
from uuid import uuid4

ROOT = Path(__file__).parent
STATIC_DIR = ROOT / "static"


@dataclass
class AuditEntry:
    id: str
    timestamp: str
    user: str
    action: str
    event_id: str | None
    changes: dict[str, Any]


@dataclass
class EventRecord:
    id: str
    name: str
    format: str
    time_controls: str
    capacity: int
    registration_open_at: str
    registration_close_at: str
    registration_open: bool = False
    status: str = "draft"
    participants: list[str] = field(default_factory=list)
    published_rounds: list[int] = field(default_factory=list)
    report_overrides: list[dict[str, Any]] = field(default_factory=list)


EVENTS: dict[str, EventRecord] = {}
AUDIT_LOG: list[AuditEntry] = []


def now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def write_audit(user: str, action: str, event_id: str | None, changes: dict[str, Any]) -> None:
    AUDIT_LOG.append(
        AuditEntry(
            id=str(uuid4()),
            timestamp=now_iso(),
            user=user,
            action=action,
            event_id=event_id,
            changes=changes,
        )
    )


def event_to_dict(event: EventRecord) -> dict[str, Any]:
    return asdict(event)


def parse_json(handler: BaseHTTPRequestHandler) -> dict[str, Any]:
    length = int(handler.headers.get("Content-Length", "0"))
    body = handler.rfile.read(length) if length else b"{}"
    return json.loads(body.decode("utf-8") or "{}")


def require_admin(handler: BaseHTTPRequestHandler) -> str | None:
    role = handler.headers.get("X-Role", "viewer").lower()
    user = handler.headers.get("X-User", "anonymous")
    if role != "admin":
        send_json(handler, HTTPStatus.FORBIDDEN, {"detail": "Admin role required"})
        return None
    return user


def send_json(handler: BaseHTTPRequestHandler, code: int, payload: Any) -> None:
    data = json.dumps(payload).encode("utf-8")
    handler.send_response(code)
    handler.send_header("Content-Type", "application/json")
    handler.send_header("Content-Length", str(len(data)))
    handler.end_headers()
    handler.wfile.write(data)


def send_file(handler: BaseHTTPRequestHandler, path: Path, content_type: str) -> None:
    if not path.exists():
        handler.send_error(404)
        return
    data = path.read_bytes()
    handler.send_response(200)
    handler.send_header("Content-Type", content_type)
    handler.send_header("Content-Length", str(len(data)))
    handler.end_headers()
    handler.wfile.write(data)


class AdminHandler(BaseHTTPRequestHandler):
    def do_GET(self) -> None:  # noqa: N802
        parsed = urlparse(self.path)
        if parsed.path == "/":
            send_file(self, STATIC_DIR / "index.html", "text/html; charset=utf-8")
            return
        if parsed.path == "/static/app.js":
            send_file(self, STATIC_DIR / "app.js", "application/javascript; charset=utf-8")
            return
        if parsed.path == "/static/styles.css":
            send_file(self, STATIC_DIR / "styles.css", "text/css; charset=utf-8")
            return
        if parsed.path == "/api/admin/events":
            send_json(self, 200, [event_to_dict(event) for event in EVENTS.values()])
            return
        if parsed.path == "/api/admin/audit-log":
            user = require_admin(self)
            if not user:
                return
            write_audit(user, "audit.read", None, {"count": len(AUDIT_LOG)})
            send_json(self, 200, [asdict(entry) for entry in AUDIT_LOG])
            return
        self.send_error(404)

    def do_POST(self) -> None:  # noqa: N802
        parsed = urlparse(self.path)
        if parsed.path == "/api/admin/events":
            user = require_admin(self)
            if not user:
                return
            payload = parse_json(self)
            required = ["name", "format", "time_controls", "capacity", "registration_open_at", "registration_close_at"]
            if any(field not in payload for field in required):
                send_json(self, 400, {"detail": "Missing required fields"})
                return
            event = EventRecord(id=str(uuid4()), **payload)
            EVENTS[event.id] = event
            write_audit(user, "event.create", event.id, {"after": event_to_dict(event)})
            send_json(self, 200, event_to_dict(event))
            return

        parts = [p for p in parsed.path.split("/") if p]
        if len(parts) >= 4 and parts[0:3] == ["api", "admin", "events"]:
            user = require_admin(self)
            if not user:
                return
            event_id = parts[3]
            event = EVENTS.get(event_id)
            if not event:
                send_json(self, 404, {"detail": "Event not found"})
                return
            tail = parts[4:]
            payload = parse_json(self)
            if tail == ["registration", "open"]:
                event.registration_open = True
                write_audit(user, "registration.open", event.id, {"registration_open": True})
                send_json(self, 200, event_to_dict(event))
                return
            if tail == ["registration", "close"]:
                event.registration_open = False
                write_audit(user, "registration.close", event.id, {"registration_open": False})
                send_json(self, 200, event_to_dict(event))
                return
            if tail == ["participants", "add"]:
                participant = payload.get("participant", "")
                if participant in event.participants:
                    send_json(self, 409, {"detail": "Participant already added"})
                    return
                if len(event.participants) >= event.capacity:
                    send_json(self, 409, {"detail": "Event is at capacity"})
                    return
                event.participants.append(participant)
                write_audit(user, "participant.add", event.id, {"participant": participant})
                send_json(self, 200, event_to_dict(event))
                return
            if tail == ["participants", "remove"]:
                participant = payload.get("participant", "")
                if participant not in event.participants:
                    send_json(self, 404, {"detail": "Participant not found"})
                    return
                event.participants.remove(participant)
                write_audit(user, "participant.remove", event.id, {"participant": participant})
                send_json(self, 200, event_to_dict(event))
                return
            if tail == ["start"]:
                if event.status != "draft":
                    send_json(self, 409, {"detail": "Only draft events can be started"})
                    return
                event.status = "active"
                write_audit(user, "event.start", event.id, {"status": "active"})
                send_json(self, 200, event_to_dict(event))
                return
            if tail == ["rounds", "publish"]:
                round_number = int(payload.get("round_number", 0))
                if event.status != "active":
                    send_json(self, 409, {"detail": "Event must be active to publish rounds"})
                    return
                if round_number in event.published_rounds:
                    send_json(self, 409, {"detail": "Round already published"})
                    return
                event.published_rounds.append(round_number)
                event.published_rounds.sort()
                write_audit(user, "round.publish", event.id, {"round_number": round_number})
                send_json(self, 200, event_to_dict(event))
                return
            if tail == ["overrides", "report"]:
                override = {
                    "match_id": payload.get("match_id"),
                    "reason": payload.get("reason"),
                    "result": payload.get("result"),
                }
                event.report_overrides.append(override)
                write_audit(user, "report.override", event.id, override)
                send_json(self, 200, event_to_dict(event))
                return
            if tail == ["finalize"]:
                if event.status != "active":
                    send_json(self, 409, {"detail": "Only active events can be finalized"})
                    return
                event.status = "finalized"
                write_audit(user, "event.finalize", event.id, {"status": "finalized"})
                send_json(self, 200, event_to_dict(event))
                return

        self.send_error(404)

    def do_PUT(self) -> None:  # noqa: N802
        parsed = urlparse(self.path)
        parts = [p for p in parsed.path.split("/") if p]
        if len(parts) == 4 and parts[0:3] == ["api", "admin", "events"]:
            user = require_admin(self)
            if not user:
                return
            event = EVENTS.get(parts[3])
            if not event:
                send_json(self, 404, {"detail": "Event not found"})
                return
            payload = parse_json(self)
            before = event_to_dict(event)
            for key in ["name", "format", "time_controls", "capacity", "registration_open_at", "registration_close_at"]:
                if key in payload:
                    setattr(event, key, payload[key])
            write_audit(user, "event.edit", event.id, {"before": before, "after": event_to_dict(event)})
            send_json(self, 200, event_to_dict(event))
            return
        self.send_error(404)



def run_server(port: int = 8000) -> None:
    server = ThreadingHTTPServer(("0.0.0.0", port), AdminHandler)
    print(f"Serving on http://0.0.0.0:{port}")
    server.serve_forever()


if __name__ == "__main__":
    run_server()

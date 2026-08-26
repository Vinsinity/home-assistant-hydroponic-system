"""Small read-only HTTP surface for the first standalone core slice."""

from __future__ import annotations

from copy import deepcopy
import hmac
from http import HTTPStatus
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
import json
import signal
from typing import Any
from urllib.parse import urlsplit

from custom_components.hydroponic_system.journal import active_cultivation

from . import __version__
from .storage import GrowAsistStore


_LANDING_PAGE = """<!doctype html>
<html lang="tr"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width">
<title>GrowAsist Core</title><style>
body{margin:0;background:#101310;color:#eef3ee;font:16px/1.5 system-ui,sans-serif}main{max-width:720px;margin:12vh auto;padding:32px}
small{color:#91a094}code{color:#58c7a2}section{margin-top:28px;padding-top:22px;border-top:1px solid #29312b}
</style></head><body><main><small>RASPBERRY PI · STANDALONE CORE</small><h1>GrowAsist çalışıyor</h1>
<p>Bu ilk çekirdek dilimi Home Assistant olmadan çalışır. Otomatik ekipman kontrolü kapalıdır.</p>
<section><b>Sağlık kontrolü</b><p><code>GET /api/v1/health</code></p>
<small>Yetiştirme verileri kimlik doğrulaması olmadan yayınlanmaz.</small></section></main></body></html>"""


def _system_summary(state: dict[str, Any]) -> dict[str, Any]:
    active = active_cultivation(state)
    cultivations = state.get("cultivations", {})
    return {
        "mode": "standalone",
        "version": __version__,
        "engine_enabled": False,
        "active_stage": state.get("active_stage"),
        "active_cultivation": deepcopy(active),
        "cultivation_count": len(cultivations.get("records", {})),
        "journal_event_count": len(state.get("events", [])),
    }


def build_handler(store: GrowAsistStore, api_token: str):
    """Create a request handler bound to one store and token."""

    class GrowAsistHandler(BaseHTTPRequestHandler):
        server_version = "GrowAsistCore"

        def _send_bytes(
            self, status: HTTPStatus, body: bytes, content_type: str
        ) -> None:
            self.send_response(status.value)
            self.send_header("Content-Type", content_type)
            self.send_header("Content-Length", str(len(body)))
            self.send_header("Cache-Control", "no-store")
            self.send_header("X-Content-Type-Options", "nosniff")
            self.send_header("X-Frame-Options", "DENY")
            self.end_headers()
            self.wfile.write(body)

        def _send_json(self, status: HTTPStatus, value: Any) -> None:
            body = json.dumps(value, ensure_ascii=False, separators=(",", ":")).encode()
            self._send_bytes(status, body, "application/json; charset=utf-8")

        def _authorized(self) -> bool:
            supplied = self.headers.get("Authorization", "")
            expected = f"Bearer {api_token}"
            return bool(api_token) and hmac.compare_digest(supplied, expected)

        def do_GET(self) -> None:  # noqa: N802 - stdlib handler API
            path = urlsplit(self.path).path
            try:
                if path == "/":
                    self._send_bytes(
                        HTTPStatus.OK,
                        _LANDING_PAGE.encode(),
                        "text/html; charset=utf-8",
                    )
                    return
                if path == "/api/v1/health":
                    health = store.health()
                    public = {
                        "ok": health["ok"],
                        "service": "growasist-core",
                        "version": __version__,
                    }
                    self._send_json(
                        HTTPStatus.OK if health["ok"] else HTTPStatus.SERVICE_UNAVAILABLE,
                        public,
                    )
                    return
                if not self._authorized():
                    self._send_json(
                        HTTPStatus.UNAUTHORIZED,
                        {"error": "A valid Bearer token is required"},
                    )
                    return
                if path == "/api/v1/system":
                    self._send_json(HTTPStatus.OK, _system_summary(store.load_state()))
                    return
                if path == "/api/v1/journal/export":
                    self._send_json(HTTPStatus.OK, store.export_journal())
                    return
                self._send_json(HTTPStatus.NOT_FOUND, {"error": "Not found"})
            except (BrokenPipeError, ConnectionResetError):
                return
            except Exception as error:  # Keep health failures observable to the caller.
                self._send_json(
                    HTTPStatus.INTERNAL_SERVER_ERROR,
                    {"error": type(error).__name__, "message": str(error)},
                )

        def do_POST(self) -> None:  # noqa: N802 - stdlib handler API
            self._send_json(
                HTTPStatus.METHOD_NOT_ALLOWED,
                {"error": "The first standalone API slice is read-only"},
            )

        def log_message(self, message: str, *args: Any) -> None:
            print(f"{self.address_string()} - {message % args}")

    return GrowAsistHandler


def serve(
    store: GrowAsistStore,
    *,
    host: str,
    port: int,
    api_token: str,
) -> None:
    """Run the standalone HTTP service until interrupted."""
    if host not in {"127.0.0.1", "::1", "localhost"} and not api_token:
        raise ValueError("A non-empty API token is required for LAN binding")
    store.initialize()
    server = ThreadingHTTPServer((host, port), build_handler(store, api_token))
    server.daemon_threads = True

    def _request_stop(_signal_number: int, _frame: Any) -> None:
        raise KeyboardInterrupt

    previous_sigterm = signal.signal(signal.SIGTERM, _request_stop)
    print(f"GrowAsist Core {__version__} listening on http://{host}:{port}")
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        pass
    finally:
        signal.signal(signal.SIGTERM, previous_sigterm)
        server.server_close()

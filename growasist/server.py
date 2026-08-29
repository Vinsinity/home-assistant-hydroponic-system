"""Authenticated HTTP API and local web application for GrowAsist Core."""

from __future__ import annotations

from copy import deepcopy
import hmac
from http import HTTPStatus
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from importlib import resources
import json
import signal
from typing import Any
from urllib.parse import urlsplit

from custom_components.hydroponic_system.journal import active_cultivation

from . import __version__
from .service import GrowAsistService
from .storage import GrowAsistStore


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


def build_handler(
    store: GrowAsistStore, api_token: str, service: GrowAsistService | None = None
):
    """Create a request handler bound to one store and token."""
    application = service or GrowAsistService(store)
    web_root = resources.files("growasist.web")
    assets = {
        "/": (web_root / "index.html", "text/html; charset=utf-8"),
        "/assets/app.css": (web_root / "app.css", "text/css; charset=utf-8"),
        "/assets/app.js": (web_root / "app.js", "text/javascript; charset=utf-8"),
        "/assets/icon.svg": (web_root / "icon.svg", "image/svg+xml"),
    }

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
            self.send_header("Referrer-Policy", "no-referrer")
            self.send_header(
                "Content-Security-Policy",
                "default-src 'self'; script-src 'self'; style-src 'self'; "
                "connect-src 'self'; img-src 'self' data:; "
                "frame-ancestors 'none'; base-uri 'none'; form-action 'self'",
            )
            self.end_headers()
            self.wfile.write(body)

        def _send_json(self, status: HTTPStatus, value: Any) -> None:
            body = json.dumps(value, ensure_ascii=False, separators=(",", ":")).encode()
            self._send_bytes(status, body, "application/json; charset=utf-8")

        def _authorized(self) -> bool:
            supplied = self.headers.get("Authorization", "")
            expected = f"Bearer {api_token}"
            return bool(api_token) and hmac.compare_digest(supplied, expected)

        def _read_json(self) -> dict[str, Any]:
            try:
                length = int(self.headers.get("Content-Length", "0"))
            except ValueError as error:
                raise ValueError("Geçersiz Content-Length") from error
            if not 0 < length <= 1_048_576:
                raise ValueError("İstek gövdesi boş veya çok büyük")
            try:
                value = json.loads(self.rfile.read(length))
            except json.JSONDecodeError as error:
                raise ValueError("Geçerli bir JSON nesnesi gönderin") from error
            if not isinstance(value, dict):
                raise ValueError("JSON gövdesi bir nesne olmalı")
            return value

        def _require_authorization(self) -> bool:
            if self._authorized():
                return True
            self._send_json(
                HTTPStatus.UNAUTHORIZED,
                {"error": "Geçerli bir Bearer token gerekli"},
            )
            return False

        def do_GET(self) -> None:  # noqa: N802 - stdlib handler API
            path = urlsplit(self.path).path
            try:
                if path in assets:
                    asset, content_type = assets[path]
                    self._send_bytes(HTTPStatus.OK, asset.read_bytes(), content_type)
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
                if not self._require_authorization():
                    return
                if path == "/api/v1/bootstrap":
                    self._send_json(HTTPStatus.OK, application.bootstrap())
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
            path = urlsplit(self.path).path
            if not self._require_authorization():
                return
            try:
                payload = self._read_json()
                routes = {
                    "/api/v1/cultivations/start": application.start_cultivation,
                    "/api/v1/cultivations/finish": application.finish_cultivation,
                    "/api/v1/cultivations/stage": application.select_stage,
                    "/api/v1/journal/events": application.append_journal_event,
                    "/api/v1/system-profile": application.update_system_profile,
                    "/api/v1/grow-profiles": application.update_grow_profile,
                    "/api/v1/grow-profiles/remove": application.remove_grow_profile,
                    "/api/v1/plants": application.update_plant,
                    "/api/v1/nutrients/catalog/add": application.add_catalog_nutrient,
                    "/api/v1/nutrients/inventory": application.update_nutrient_inventory,
                    "/api/v1/nutrient-programs/add": application.add_nutrient_program,
                    "/api/v1/hardware": application.update_hardware,
                    "/api/v1/i2c/discover": application.discover_i2c,
                    "/api/v1/i2c/enroll": application.enroll_i2c_device,
                    "/api/v1/i2c/remove": application.remove_i2c_device,
                    "/api/v1/network/discover": application.discover_network,
                    "/api/v1/network/enroll": application.enroll_network_device,
                    "/api/v1/network/remove": application.remove_network_device,
                    "/api/v1/dosing/test": application.test_pump,
                    "/api/v1/dosing/calibration/start": application.start_pump_calibration,
                    "/api/v1/dosing/calibration/complete": application.complete_pump_calibration,
                }
                operation = routes.get(path)
                if operation is None:
                    self._send_json(HTTPStatus.NOT_FOUND, {"error": "Not found"})
                    return
                result = operation(payload)
                self._send_json(HTTPStatus.OK, {"ok": True, "result": result})
            except ValueError as error:
                self._send_json(
                    HTTPStatus.BAD_REQUEST,
                    {"error": type(error).__name__, "message": str(error)},
                )
            except (BrokenPipeError, ConnectionResetError):
                return
            except Exception as error:
                self._send_json(
                    HTTPStatus.INTERNAL_SERVER_ERROR,
                    {"error": type(error).__name__, "message": str(error)},
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
    if not api_token:
        raise ValueError("A non-empty API token is required")
    store.initialize()
    service = GrowAsistService(store)
    try:
        service.discover_i2c({"automatic": True})
    except Exception as error:
        # Hardware availability must remain observable in the UI without making
        # the journal application unavailable.
        print(f"I2C startup discovery failed: {type(error).__name__}: {error}")
    server = ThreadingHTTPServer(
        (host, port), build_handler(store, api_token, service)
    )
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

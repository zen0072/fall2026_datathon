"""Same-origin local API and static frontend; no model training on web requests."""

import json
import mimetypes
import sys
import ipaddress
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import parse_qs, unquote, urlsplit

from .schema import AppError
from .chat import ChatSettings, answer as chat_answer, config as chat_config

STATIC = Path(__file__).parent / "static"
MAX_IMPORT_BYTES = 128 * 1024 * 1024


def make_server(store, host="127.0.0.1", port=8000):
    chat_settings = ChatSettings()

    class Handler(BaseHTTPRequestHandler):
        server_version = "AccessWorkspace/1.0"

        def _send(self, status, content, content_type="application/json; charset=utf-8", **headers):
            if isinstance(content, (dict, list)):
                content = json.dumps(content, ensure_ascii=False, allow_nan=False).encode("utf-8")
            elif isinstance(content, str):
                content = content.encode("utf-8")
            self.send_response(status)
            self.send_header("Content-Type", content_type)
            self.send_header("Content-Length", str(len(content)))
            self.send_header("Cache-Control", "no-store" if self.path.startswith("/api/") else "no-cache")
            self.send_header("X-Content-Type-Options", "nosniff")
            self.send_header("Referrer-Policy", "no-referrer")
            self.send_header("Content-Security-Policy", "default-src 'self'; script-src 'self'; style-src 'self' 'unsafe-inline'; img-src 'self' data: https://server.arcgisonline.com; connect-src 'self'; object-src 'none'; base-uri 'self'; frame-ancestors 'self'")
            for key, value in headers.items():
                self.send_header(key.replace("_", "-"), value)
            self.end_headers()
            self.wfile.write(content)

        def _check_origin(self):
            # Protect the loopback app from cross-origin browser writes/rebinding.
            authority = urlsplit("http://" + self.headers.get("Host", ""))
            allowed_hosts = {"localhost", "127.0.0.1", "::1", host}
            if authority.hostname not in allowed_hosts:
                raise AppError("Unexpected Host header.", 403)
            origin = self.headers.get("Origin")
            if origin:
                parsed = urlsplit(origin)
                if parsed.scheme not in ("http", "https") or parsed.netloc != authority.netloc:
                    raise AppError("Cross-origin requests are not allowed.", 403)

        def _json_body(self):
            if self.headers.get_content_type() != "application/json":
                raise AppError("Send an application/json request.", 415)
            try:
                length = int(self.headers.get("Content-Length", "0"))
            except ValueError as error:
                raise AppError("Invalid request length.") from error
            maximum = MAX_IMPORT_BYTES if urlsplit(self.path).path == "/api/import" else 64 * 1024
            if length <= 0 or length > maximum:
                raise AppError("The request is empty or exceeds the size limit.", 413)
            try:
                return json.loads(self.rfile.read(length), parse_constant=lambda value: (_ for _ in ()).throw(ValueError(value)))
            except (ValueError, UnicodeDecodeError) as error:
                raise AppError("Invalid JSON request.") from error

        def _can_configure_chat(self):
            return (host in {"localhost", "127.0.0.1", "::1"}
                    and ipaddress.ip_address(self.client_address[0]).is_loopback)

        def _chat_config(self):
            return {**chat_config(chat_settings.credentials()),
                    "configurable": self._can_configure_chat()}

        def _handle(self):
            self._check_origin()
            parsed = urlsplit(self.path)
            path = unquote(parsed.path)
            query = {key: values[-1] for key, values in parse_qs(parsed.query).items()}
            if self.command == "GET":
                if path == "/api/chat/config":
                    return self._send(200, self._chat_config())
                if path == "/api/health":
                    return self._send(200, {"ok": True, "storage": "duckdb"})
                if path == "/api/metadata":
                    return self._send(200, store.metadata())
                if path == "/api/places":
                    for field in ("limit", "offset"):
                        if field in query:
                            try:
                                query[field] = int(query[field])
                            except ValueError as error:
                                raise AppError(f"Invalid {field}.") from error
                    allowed = {"aspect", "service", "search", "status", "sort", "limit", "offset"}
                    if set(query) - allowed:
                        raise AppError("Unknown location filter.")
                    return self._send(200, store.list_places(**query))
                if path.startswith("/api/places/"):
                    try:
                        evidence_offset = int(query.get("evidence_offset", 0))
                    except ValueError as error:
                        raise AppError("Invalid evidence offset.") from error
                    return self._send(200, store.place_detail(path[len("/api/places/"):], query.get("aspect", "physical"), query.get("snapshot_id"), evidence_state=query.get("evidence_state", "all"), evidence_offset=evidence_offset))
                if path == "/api/work-items.csv":
                    return self._send(200, store.export_work_items(), "text/csv; charset=utf-8", Content_Disposition='attachment; filename="access-work-queue.csv"')
                if path == "/api/work-items":
                    return self._send(200, {"items": store.list_work_items(query.get("status", "all"))})
                if path.startswith("/api/work-items/"):
                    return self._send(200, store.get_work_item(path[len("/api/work-items/"):]))
                if path.startswith("/api/"):
                    raise AppError("API endpoint not found.", 404)
                relative = "index.html" if path == "/" else path.lstrip("/")
                target = (STATIC / relative).resolve()
                if not target.is_relative_to(STATIC.resolve()) or not target.is_file():
                    raise AppError("Page not found.", 404)
                return self._send(200, target.read_bytes(), mimetypes.guess_type(target.name)[0] or "application/octet-stream")
            if self.command == "POST" and path == "/api/chat":
                return self._send(200, chat_answer(store, self._json_body(), chat_settings.credentials()))
            if self.command == "POST" and path == "/api/chat/config":
                if not self._can_configure_chat():
                    raise AppError("API keys can only be entered on a loopback-bound local server.", 403)
                chat_settings.configure(self._json_body())
                return self._send(200, self._chat_config())
            if self.command == "POST" and path == "/api/import":
                return self._send(200, store.import_bundle(self._json_body()))
            if self.command == "POST" and path == "/api/work-items":
                return self._send(201, store.create_work_item(self._json_body()))
            if self.command == "PATCH" and path.startswith("/api/work-items/"):
                return self._send(200, store.update_work_item(path[len("/api/work-items/"):], self._json_body()))
            raise AppError("API endpoint not found.", 404)

        def _dispatch(self):
            try:
                self._handle()
            except AppError as error:
                self._send(error.status, {"error": str(error), **error.details})
            except (BrokenPipeError, ConnectionResetError):
                pass
            except Exception as error:
                print(f"Request failed: {type(error).__name__}: {error}", file=sys.stderr)
                self._send(500, {"error": "The request could not be completed. Check the local server log."})

        do_GET = _dispatch
        do_POST = _dispatch
        do_PATCH = _dispatch

    server = ThreadingHTTPServer((host, port), Handler)
    server.daemon_threads = True
    return server

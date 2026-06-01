from __future__ import annotations

import json
import threading
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from typing import Any
from urllib.parse import urlparse

from .jobs import LightroomJobs


API_VERSION = "1"


class LightroomBridgeServer:
    def __init__(self, jobs: LightroomJobs, port: int = 38387):
        self.jobs = jobs
        self.port = port
        self._server: ThreadingHTTPServer | None = None
        self._thread: threading.Thread | None = None


    def start(self) -> None:
        if self._server is not None:
            return

        handler = self._handler_class()
        try:
            self._server = ThreadingHTTPServer(("127.0.0.1", self.port), handler)
        except OSError:
            self._server = ThreadingHTTPServer(("127.0.0.1", 0), handler)
            self.port = int(self._server.server_address[1])

        self._thread = threading.Thread(target=self._server.serve_forever, daemon=True)
        self._thread.start()


    def status(self) -> dict[str, Any]:
        return {"running": self._server is not None, "host": "127.0.0.1", "port": self.port, "apiVersion": API_VERSION}


    def _handler_class(self):
        bridge = self

        class Handler(BaseHTTPRequestHandler):
            def do_GET(self) -> None:
                bridge._handle(self)


            def do_POST(self) -> None:
                bridge._handle(self)


            def log_message(self, _format: str, *_args: Any) -> None:
                return

        return Handler


    def _handle(self, handler: BaseHTTPRequestHandler) -> None:
        try:
            parsed = urlparse(handler.path)
            path = parsed.path
            if path == "/api/lightroom/health" and handler.command == "GET":
                self._write_json(handler, {"state": "ok", **self.status()})
                return

            if path == "/api/lightroom/jobs" and handler.command == "POST":
                request = self._read_json(handler)
                self._write_json(handler, self.jobs.start(request))
                return

            job_status_prefix = "/api/lightroom/jobs/"
            if path.startswith(job_status_prefix) and handler.command == "GET":
                suffix = path[len(job_status_prefix):]
                parts = suffix.split("/")
                if len(parts) == 2 and parts[1] == "status":
                    self._write_json(handler, self.jobs.status(parts[0]))
                    return

                if len(parts) == 2 and parts[1] == "results":
                    self._write_json(handler, self.jobs.results(parts[0]))
                    return

            if path.startswith(job_status_prefix) and handler.command == "POST":
                suffix = path[len(job_status_prefix):]
                parts = suffix.split("/")
                if len(parts) == 2 and parts[1] == "client-log":
                    request = self._read_json(handler)
                    self._write_json(handler, self.jobs.client_log(parts[0], request))
                    return

            self._write_json(handler, {"state": "error", "message": "Not found."}, 404)
        except Exception as exc:
            self._write_json(handler, {"state": "error", "message": str(exc)}, 500)


    def _read_json(self, handler: BaseHTTPRequestHandler) -> dict[str, Any]:
        length = int(handler.headers.get("Content-Length", "0"))
        raw = handler.rfile.read(length).decode("utf-8") if length else "{}"
        payload = json.loads(raw)
        if not isinstance(payload, dict):
            raise ValueError("JSON body must be an object.")

        return payload


    def _write_json(self, handler: BaseHTTPRequestHandler, payload: dict[str, Any], status: int = 200) -> None:
        body = json.dumps(payload, ensure_ascii=False).encode("utf-8")
        handler.send_response(status)
        handler.send_header("Content-Type", "application/json; charset=utf-8")
        handler.send_header("Content-Length", str(len(body)))
        handler.end_headers()
        handler.wfile.write(body)

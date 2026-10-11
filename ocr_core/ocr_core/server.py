"""백엔드가 스트림 읽기를 시작·중지하는 HTTP API. 한 번에 한 경기만 읽습니다.

POST   /streams   {"url": "...", "teams": [{"code": "GBA", "names": ["경북 어센더스", "Gyeongbuk Ascension"]}, ...]}
                  → 202 시작 / 400 요청 오류 / 409 이미 읽는 중
GET    /streams   → 현재(또는 마지막) 세션 상태
DELETE /streams   → 읽기 중지

바뀐 값은 지금은 이 프로세스의 콘솔(stdout)에 찍습니다. 백엔드로 보내는 이벤트 형식은 아직 정하지 않았습니다.
"""

from __future__ import annotations

import json
import threading
from dataclasses import asdict
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

from .config import Config
from .stream import StreamSession
from .teams import teams_from_request

MAX_BODY = 64 * 1024


class StreamManager:
    def __init__(self, config: Config):
        self.config = config
        self.session: StreamSession | None = None
        self._lock = threading.Lock()

    def start(self, body: object) -> StreamSession:
        if not isinstance(body, dict) or not isinstance(body.get("url"), str) or not body["url"].strip():
            raise ValueError("url 이 필요합니다")
        teams = teams_from_request(body.get("teams"))
        with self._lock:
            if self.session and self.session.active:
                raise RuntimeError("이미 다른 스트림을 읽고 있습니다")
            self.session = StreamSession(body["url"].strip(), teams, self.config)
            self.session.start()
            return self.session

    def stop(self) -> StreamSession | None:
        with self._lock:
            session = self.session
        if session and session.active:
            session.stop()
        return session


def make_handler(manager: StreamManager) -> type[BaseHTTPRequestHandler]:
    class Handler(BaseHTTPRequestHandler):
        def _send(self, code: int, payload: dict) -> None:
            data = json.dumps(payload, ensure_ascii=False).encode()
            self.send_response(code)
            self.send_header("Content-Type", "application/json; charset=utf-8")
            self.send_header("Content-Length", str(len(data)))
            self.end_headers()
            self.wfile.write(data)

        def _status(self) -> dict:
            s = manager.session
            return {"session": asdict(s.status) if s else None}

        def do_GET(self) -> None:
            if self.path != "/streams":
                return self._send(404, {"error": "not found"})
            self._send(200, self._status())

        def do_POST(self) -> None:
            if self.path != "/streams":
                return self._send(404, {"error": "not found"})
            length = int(self.headers.get("Content-Length") or 0)
            if length <= 0 or length > MAX_BODY:
                return self._send(400, {"error": "JSON 본문이 필요합니다"})
            try:
                body = json.loads(self.rfile.read(length))
                manager.start(body)
            except (ValueError, json.JSONDecodeError) as e:
                return self._send(400, {"error": str(e)})
            except RuntimeError as e:
                return self._send(409, {"error": str(e), **self._status()})
            self._send(202, self._status())

        def do_DELETE(self) -> None:
            if self.path != "/streams":
                return self._send(404, {"error": "not found"})
            manager.stop()
            self._send(200, self._status())

        def log_message(self, fmt: str, *args) -> None:
            print(f"[http] {self.address_string()} {fmt % args}", flush=True)

    return Handler


def serve(host: str, port: int, config: Config) -> None:
    manager = StreamManager(config)
    server = ThreadingHTTPServer((host, port), make_handler(manager))
    print(f"[http] {host}:{port} 에서 대기 중", flush=True)
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        pass
    finally:
        manager.stop()
        server.server_close()

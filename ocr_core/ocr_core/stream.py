"""스트림 URL → ffmpeg 로 프레임 추출 → OcrCore → 바뀐 값만 출력.

- 유튜브 링크는 yt-dlp 로 실제 영상 주소(라이브는 HLS)를 얻은 뒤 ffmpeg 에 넘깁니다.
- 로컬 파일이나 그 밖의 URL 은 ffmpeg 에 바로 넘깁니다.
- ffmpeg 가 설정한 fps 로 프레임을 뽑아 1920×1080 BGR 원시 바이트로 내보냅니다.
- 라이브는 OCR 이 따라가지 못하면 밀린 프레임을 버리고 가장 최근 프레임만 읽습니다.
  파일(VOD)은 버리지 않고 뽑은 프레임을 모두 읽습니다.
- tesseract 엔진은 세션을 시작할 때 띄우고 스트림이 끝날 때까지 유지합니다.
"""

from __future__ import annotations

import os
import queue
import shutil
import subprocess
import threading
from dataclasses import dataclass, field
from typing import Callable, Iterator
from urllib.parse import urlparse

import numpy as np

from .changes import ChangeTracker, FrameChanges, format_changes
from .config import Config
from .pipeline import OcrCore

YOUTUBE_HOSTS = ("youtube.com", "youtu.be")


@dataclass
class Source:
    url: str  # ffmpeg 에 넘길 주소
    live: bool
    headers: dict[str, str] = field(default_factory=dict)
    title: str | None = None


def is_youtube(url: str) -> bool:
    host = (urlparse(url).hostname or "").lower()
    return any(host == h or host.endswith("." + h) for h in YOUTUBE_HOSTS)


def resolve_source(url: str, ytdlp_format: str) -> Source:
    if os.path.exists(url):
        return Source(url=url, live=False)
    if not is_youtube(url):
        return Source(url=url, live=True)  # 그 밖의 URL 은 라이브로 보고 밀린 프레임을 버림

    try:
        import yt_dlp
    except ImportError as e:
        raise RuntimeError("유튜브 링크를 읽으려면 yt-dlp 가 필요합니다: pip install yt-dlp") from e
    opts = {"format": ytdlp_format, "quiet": True, "no_warnings": True, "noplaylist": True}
    with yt_dlp.YoutubeDL(opts) as ydl:
        info = ydl.extract_info(url, download=False)
    if not info.get("url"):
        raise RuntimeError(f"영상 주소를 얻지 못했습니다 (format={ytdlp_format})")
    return Source(
        url=info["url"],
        live=bool(info.get("is_live")),
        headers=dict(info.get("http_headers") or {}),
        title=info.get("title"),
    )


def ffmpeg_command(source: Source, fps: float, size: tuple[int, int], cmd: str = "ffmpeg") -> list[str]:
    w, h = size
    args = [cmd, "-hide_banner", "-loglevel", "error", "-nostdin"]
    if source.url.startswith(("http://", "https://")):
        args += ["-reconnect", "1", "-reconnect_streamed", "1", "-reconnect_delay_max", "5"]
        if source.headers:
            args += ["-headers", "".join(f"{k}: {v}\r\n" for k, v in source.headers.items())]
    args += [
        "-i", source.url,
        "-an", "-sn",
        "-vf", f"fps={fps},scale={w}:{h}",
        "-pix_fmt", "bgr24", "-f", "rawvideo", "pipe:1",
    ]
    return args


class FrameReader:
    """ffmpeg 출력에서 프레임을 하나씩 꺼냅니다. (번호, 스트림 위치 초, 프레임)."""

    def __init__(self, source: Source, fps: float, size: tuple[int, int], ffmpeg: str = "ffmpeg", buffer: int = 8):
        if shutil.which(ffmpeg) is None:
            raise RuntimeError(f"{ffmpeg} 를 찾을 수 없습니다")
        self.source, self.fps, self.size = source, fps, size
        self.dropped = 0
        self._proc = subprocess.Popen(
            ffmpeg_command(source, fps, size, ffmpeg), stdout=subprocess.PIPE, stderr=subprocess.PIPE
        )
        # 라이브: 최신 1장만 보관(밀리면 버림) / 파일: 버리지 않고 기다림
        self._queue: queue.Queue = queue.Queue(maxsize=1 if source.live else buffer)
        self._stopped = threading.Event()
        self._stderr: list[str] = []
        threading.Thread(target=self._read, daemon=True).start()
        threading.Thread(target=self._drain_stderr, daemon=True).start()

    def _read(self) -> None:
        w, h = self.size
        nbytes = w * h * 3
        index = 0
        stdout = self._proc.stdout
        try:
            while not self._stopped.is_set():
                buf = stdout.read(nbytes)
                if len(buf) < nbytes:
                    break
                item = (index, index / self.fps, np.frombuffer(buf, np.uint8).reshape(h, w, 3))
                index += 1
                if self.source.live:
                    try:
                        self._queue.get_nowait()
                        self.dropped += 1
                    except queue.Empty:
                        pass
                    self._queue.put_nowait(item)
                else:
                    while not self._stopped.is_set():
                        try:
                            self._queue.put(item, timeout=0.5)
                            break
                        except queue.Full:
                            continue
        finally:
            self._put_end()

    def _put_end(self) -> None:
        while True:
            try:
                self._queue.put(None, timeout=0.5)
                return
            except queue.Full:
                if self._stopped.is_set():
                    return

    def _drain_stderr(self) -> None:
        for line in self._proc.stderr:
            self._stderr.append(line.decode("utf-8", "replace").rstrip())
            del self._stderr[:-20]

    @property
    def error(self) -> str | None:
        code = self._proc.poll()
        if code not in (None, 0) and not self._stopped.is_set():
            return f"ffmpeg 종료 코드 {code}: " + " / ".join(self._stderr[-3:])
        return None

    def __iter__(self) -> Iterator[tuple[int, float, np.ndarray]]:
        while True:
            try:
                item = self._queue.get(timeout=0.5)
            except queue.Empty:
                if self._stopped.is_set():
                    return
                continue
            if item is None:
                return
            yield item

    def close(self) -> None:
        self._stopped.set()
        if self._proc.poll() is None:
            self._proc.terminate()
            try:
                self._proc.wait(timeout=5)
            except subprocess.TimeoutExpired:
                self._proc.kill()


@dataclass
class SessionStatus:
    url: str
    state: str = "starting"  # starting | running | ended | stopped | failed
    title: str | None = None
    live: bool | None = None
    frames: int = 0
    dropped: int = 0
    last_ms: float = 0.0
    error: str | None = None


class StreamSession:
    """스트림 하나를 끝까지 읽습니다. run() 은 블로킹, start() 는 백그라운드 스레드."""

    def __init__(
        self,
        url: str,
        teams: list[dict] | None,
        config: Config | None = None,
        on_frame: Callable[[FrameChanges], None] | None = None,
    ):
        self.url = url
        self.teams = teams
        self.config = config or Config.load()
        self.on_frame = on_frame or print_changes
        self.status = SessionStatus(url=url)
        self._stop = threading.Event()
        self._reader: FrameReader | None = None
        self._thread: threading.Thread | None = None

    def start(self) -> None:
        self._thread = threading.Thread(target=self._run_safe, daemon=True)
        self._thread.start()

    def _run_safe(self) -> None:
        try:
            self.run()
        except Exception as e:  # 백그라운드 세션의 실패는 상태로 알림
            self.status.state, self.status.error = "failed", str(e)
            print(f"[stream] 실패: {e}", flush=True)

    def run(self) -> SessionStatus:
        sc = self.config.layout.get("stream", {})
        fps = float(sc.get("fps", 1))
        source = resolve_source(self.url, sc.get("ytdlp_format", "bv*[height<=1080]/b"))
        self.status.title, self.status.live = source.title, source.live
        if self._stop.is_set():
            self.status.state = "stopped"
            return self.status

        tracker = ChangeTracker()
        with OcrCore(self.config, teams=self.teams) as core:  # 엔진은 이 블록이 끝날 때까지 유지
            self._reader = reader = FrameReader(source, fps, self.config.frame_size, sc.get("ffmpeg", "ffmpeg"))
            self.status.state = "running"
            print(f"[stream] 시작: {source.title or self.url} ({'라이브' if source.live else '파일'}, {fps} fps)", flush=True)
            try:
                for index, position, frame in reader:
                    if self._stop.is_set():
                        break
                    result = core.process(frame)
                    self.status.frames += 1
                    self.status.last_ms = result.elapsed_ms
                    self.status.dropped = reader.dropped
                    changes = tracker.update(result, index, position)
                    if changes:
                        self.on_frame(changes)
                error = reader.error
            finally:
                reader.close()

        if self._stop.is_set():
            self.status.state = "stopped"
        elif error:
            self.status.state, self.status.error = "failed", error
        else:
            self.status.state = "ended"
        print(f"[stream] {self.status.state}: 프레임 {self.status.frames}장, 버린 프레임 {self.status.dropped}장"
              + (f", {self.status.error}" if self.status.error else ""), flush=True)
        return self.status

    def stop(self, wait: float = 10.0) -> None:
        self._stop.set()
        if self._reader:
            self._reader.close()
        if self._thread and self._thread is not threading.current_thread():
            self._thread.join(wait)

    @property
    def active(self) -> bool:
        return self.status.state in ("starting", "running")


def print_changes(fc: FrameChanges) -> None:
    print(format_changes(fc), flush=True)

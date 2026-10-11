"""명령줄 진입점.

    python -m ocr_core 프레임.png [...]              프레임마다 JSON 한 줄
    python -m ocr_core stream <URL> --teams t.json   스트림을 읽어 바뀐 값을 콘솔에 출력
    python -m ocr_core serve --port 8100             백엔드가 HTTP 로 스트림 읽기를 시작·중지
"""

from __future__ import annotations

import argparse
import json
import sys

from .config import Config
from .frame import load_image
from .pipeline import OcrCore


def parse_box(text: str) -> tuple[int, int, int, int]:
    parts = [int(v) for v in text.split(",")]
    if len(parts) != 4:
        raise argparse.ArgumentTypeError("x,y,w,h 형식이어야 합니다")
    return tuple(parts)


def frames_main(argv: list[str]) -> int:
    parser = argparse.ArgumentParser(prog="ocr_core", description="중계 프레임에서 점수 정보를 읽습니다. "
                                     "스트림은 'stream', HTTP 서버는 'serve' 하위 명령을 쓰세요.")
    parser.add_argument("images", nargs="+", help="프레임 이미지 경로")
    parser.add_argument("--config", help="설정 폴더 (기본: ocr_core/config)")
    parser.add_argument("--crop", type=parse_box, help="정규화 전 잘라낼 영역 x,y,w,h (폰 스크린샷 여백 제거용)")
    parser.add_argument("--pretty", action="store_true", help="들여쓰기해서 출력")
    args = parser.parse_args(argv)

    with OcrCore(Config.load(args.config)) as core:
        for path in args.images:
            result = core.process(load_image(path), args.crop)
            payload = {"image": path, **result.to_dict()}
            print(json.dumps(payload, ensure_ascii=False, indent=2 if args.pretty else None))
    return 0


def load_teams_file(path: str) -> list[dict]:
    """백엔드 요청과 같은 형식의 JSON. 팀 배열이거나 {"teams": [...]}."""
    from .teams import teams_from_request

    with open(path, encoding="utf-8") as f:
        data = json.load(f)
    return teams_from_request(data.get("teams") if isinstance(data, dict) else data)


def stream_main(argv: list[str]) -> int:
    from .stream import StreamSession

    parser = argparse.ArgumentParser(prog="ocr_core stream", description="스트림을 읽어 바뀐 값을 콘솔에 출력합니다.")
    parser.add_argument("url", help="유튜브 라이브/영상 링크, 영상 파일 경로, 또는 ffmpeg 가 읽는 URL")
    parser.add_argument("--teams", help="참가팀 JSON (백엔드 요청의 teams 와 같은 형식). 없으면 config/teams.yaml")
    parser.add_argument("--config", help="설정 폴더 (기본: ocr_core/config)")
    args = parser.parse_args(argv)

    teams = load_teams_file(args.teams) if args.teams else None
    session = StreamSession(args.url, teams, Config.load(args.config))
    try:
        status = session.run()
    except KeyboardInterrupt:
        session.stop()
        return 130
    return 0 if status.state in ("ended", "stopped") else 1


def serve_main(argv: list[str]) -> int:
    from .server import serve

    parser = argparse.ArgumentParser(prog="ocr_core serve", description="백엔드 요청으로 스트림을 읽는 HTTP 서버")
    parser.add_argument("--host", default="127.0.0.1")
    parser.add_argument("--port", type=int, default=8100)
    parser.add_argument("--config", help="설정 폴더 (기본: ocr_core/config)")
    args = parser.parse_args(argv)
    serve(args.host, args.port, Config.load(args.config))
    return 0


def main(argv: list[str] | None = None) -> int:
    argv = sys.argv[1:] if argv is None else argv
    if argv and argv[0] == "stream":
        return stream_main(argv[1:])
    if argv and argv[0] == "serve":
        return serve_main(argv[1:])
    return frames_main(argv)


if __name__ == "__main__":
    sys.exit(main())

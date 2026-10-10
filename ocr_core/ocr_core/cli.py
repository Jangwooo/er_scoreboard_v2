"""python -m ocr_core 프레임.png [...] → 프레임마다 JSON 한 줄."""

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


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="ocr_core", description="중계 프레임에서 점수 정보를 읽습니다.")
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


if __name__ == "__main__":
    sys.exit(main())

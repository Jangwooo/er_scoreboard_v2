"""layout.yaml 의 박스를 실제 프레임 위에 그려 좌표 보정을 돕습니다.

    python scripts/draw_layout.py samples/ingame_01.png --out /tmp/overlay.png [--crop x,y,w,h]

색: 노랑=화면 분류 probe, 하늘=슬롯 강조선 후보, 초록=슬롯 필드(선택된 위치),
    분홍=인게임 리더보드, 주황=집계표, 흰색=라운드 박스
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

import cv2

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from ocr_core.cli import parse_box  # noqa: E402
from ocr_core.config import Config  # noqa: E402
from ocr_core.frame import load_image, normalize  # noqa: E402
from ocr_core.ingame import locate_panels  # noqa: E402
from ocr_core.layout import row_box, slot_box, slot_field_box  # noqa: E402

YELLOW, CYAN, GREEN, PINK, ORANGE, WHITE = (0, 255, 255), (255, 255, 0), (0, 255, 0), (255, 0, 255), (0, 140, 255), (255, 255, 255)


def rect(img, box, color, label=""):
    x, y, w, h = box
    cv2.rectangle(img, (x, y), (x + w, y + h), color, 1)
    if label:
        cv2.putText(img, label, (x, max(10, y - 3)), cv2.FONT_HERSHEY_SIMPLEX, 0.35, color, 1, cv2.LINE_AA)


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("image")
    parser.add_argument("--out", required=True)
    parser.add_argument("--config")
    parser.add_argument("--crop", type=parse_box)
    args = parser.parse_args()

    cfg = Config.load(args.config)
    L = cfg.layout
    frame = normalize(load_image(args.image), cfg.frame_size, args.crop)
    canvas = frame.copy()

    for screen, s in L["classifier"]["screens"].items():
        for p in s["probes"]:
            rect(canvas, p["box"], YELLOW, f"{screen}.{p['name']}")

    ig = L["ingame"]
    rect(canvas, ig["round_box"], WHITE, "round")
    slots = ig["slots"]
    for i in range(slots["count"]):
        for y in slots["y_candidates"]:
            rect(canvas, slot_box(slots, i, y, slots["anchor"]["strip"]), CYAN)
    for i, y in enumerate(locate_panels(frame, slots)):
        for field in slots["fields"]:
            rect(canvas, slot_field_box(slots, i, y, field), GREEN, f"{i + 1}.{field}")
    lb = ig["leaderboard"]
    for r in range(lb["rows"]):
        rect(canvas, row_box(lb, r, lb["code_box"]), PINK, f"lb{r + 1}")
        rect(canvas, row_box(lb, r, lb["score_box"]), PINK)

    rc = L["results"]
    for r in range(rc["rows"]):
        rect(canvas, row_box(rc, r, rc["name_box"]), ORANGE, f"res{r + 1}")
        for col in rc["columns"]:
            rect(canvas, row_box(rc, r, col["box"]), ORANGE, col["name"] if r == 0 else "")

    cv2.imwrite(args.out, canvas)
    print(f"저장: {args.out}")
    return 0


if __name__ == "__main__":
    sys.exit(main())

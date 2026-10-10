"""layout.yaml 좌표대로 합성 프레임을 그립니다.

실제 중계 화면이 아니므로 실제 정확도를 보여주지는 않습니다.
좌표 계산, 분류, 추출, 검증 로직이 서로 맞물리는지 확인하는 용도입니다.
"""

from __future__ import annotations

from functools import lru_cache
from pathlib import Path

import cv2
import numpy as np

from ocr_core.layout import row_box, slot_box, slot_field_box

BG = (30, 30, 30)
TEXT = (245, 245, 245)
LABEL = (130, 130, 130)  # TS/KS 라벨처럼 흐린 글자
STRIP = (60, 40, 220)  # 팀 색 강조선
# Hershey 글꼴은 3 이 5 처럼 생겨 tesseract 가 자주 틀리므로, 방송처럼 일반 산세리프 TTF 로 그립니다
TTF = Path("/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf")


@lru_cache(maxsize=1)
def _freetype():
    if not (hasattr(cv2, "freetype") and TTF.exists()):
        return None
    ft = cv2.freetype.createFreeType2()
    ft.loadFontData(str(TTF), 0)
    return ft


def hsv_mid_bgr(low, high) -> tuple[int, int, int]:
    mid = np.uint8([[[(a + b) // 2 for a, b in zip(low, high)]]])
    return tuple(int(v) for v in cv2.cvtColor(mid, cv2.COLOR_HSV2BGR)[0, 0])


def fill(img, box, color) -> None:
    x, y, w, h = box
    cv2.rectangle(img, (x, y), (x + w - 1, y + h - 1), color, -1)


def _text_size(text: str, height: int) -> tuple[int, int]:
    ft = _freetype()
    if ft is not None:
        return ft.getTextSize(text, height, -1)[0]
    scale = height / 22
    (tw, th), _ = cv2.getTextSize(text, cv2.FONT_HERSHEY_TRIPLEX, scale, 1)
    return tw, th


def _put(img, text: str, org: tuple[int, int], height: int, color) -> None:
    ft = _freetype()
    if ft is not None:
        ft.putText(img, text, org, height, color, -1, cv2.LINE_AA, True)
    else:
        cv2.putText(img, text, org, cv2.FONT_HERSHEY_TRIPLEX, height / 22, color, 1, cv2.LINE_AA)


def draw_runs(img, box, runs: list[tuple[str, tuple[int, int, int]]], align: str = "center") -> None:
    """(글자, 색) 조각들을 이어서 박스 안에 맞는 가장 큰 크기로 씁니다."""
    x, y, w, h = box
    text = "".join(t for t, _ in runs)
    height = max(8, int(h * 0.8))
    while height > 8 and _text_size(text, height)[0] > w - 6:
        height -= 1
    tw, th = _text_size(text, height)
    cx = x + (w - tw) // 2 if align == "center" else x + w - tw - 3
    base = y + (h + th) // 2
    for t, color in runs:
        _put(img, t, (cx, base), height, color)
        cx += _text_size(t, height)[0]


def draw_text(img, box, text: str) -> None:
    draw_runs(img, box, [(text, TEXT)])


def blank(layout: dict) -> np.ndarray:
    f = layout["frame"]
    return np.full((f["height"], f["width"], 3), BG, np.uint8)


def paint_probes(img, layout: dict, screen: str) -> None:
    for p in layout["classifier"]["screens"][screen]["probes"]:
        if p["check"] == "color":
            fill(img, p["box"], hsv_mid_bgr(p["hsv_low"], p["hsv_high"]))


def fmt(v: float) -> str:
    return f"{v:.1f}"


def ingame_frame(
    layout: dict,
    round_no: int,
    slots: list[dict],
    leaderboard: list[tuple[str, float]],
    raised: set[int] = frozenset(),
    skull: np.ndarray | None = None,
):
    """slots[i] = {"name", "ts", "ks", "dead"?}; raised = 위로 올라온(관전 중) 슬롯 인덱스.

    skull(회색조 템플릿)을 주면 dead 슬롯의 해골 박스에 붙입니다.
    """
    img = blank(layout)
    paint_probes(img, layout, "ingame")
    ig = layout["ingame"]
    draw_text(img, ig["round_box"], f"LOWER MATCH | ROUND {round_no}")
    sc = ig["slots"]
    normal_y, raised_y = sc["y_candidates"][0], sc["y_candidates"][1]
    for i, s in enumerate(slots):
        y = raised_y if i in raised else normal_y
        fill(img, slot_box(sc, i, y, sc["anchor"]["strip"]), STRIP)
        runs = [("TS ", LABEL), (fmt(s["ts"]), TEXT), (" KS ", LABEL), (fmt(s["ks"]), TEXT)]
        draw_runs(img, slot_field_box(sc, i, y, "tsks"), runs, align="right")
        draw_text(img, slot_field_box(sc, i, y, "name"), s["name"])
        if skull is not None and s.get("dead"):
            x, sy, _, bh = slot_field_box(sc, i, y, "skull")
            th, tw = skull.shape
            oy = sy + (bh - th) // 2
            img[oy:oy + th, x + 20:x + 20 + tw] = cv2.cvtColor(skull, cv2.COLOR_GRAY2BGR)
    lb = ig["leaderboard"]
    for r, (code, score) in enumerate(leaderboard):
        draw_text(img, row_box(lb, r, lb["code_box"]), code)
        draw_text(img, row_box(lb, r, lb["score_box"]), f"{score:g}")
    return img


def results_frame(layout: dict, rows: list[tuple[str, dict[str, float]]]):
    img = blank(layout)
    paint_probes(img, layout, "results")
    rc = layout["results"]
    for r, (name, values) in enumerate(rows):
        draw_text(img, row_box(rc, r, rc["name_box"]), name)
        for col in rc["columns"]:
            draw_text(img, row_box(rc, r, col["box"]), fmt(values[col["name"]]))
    return img

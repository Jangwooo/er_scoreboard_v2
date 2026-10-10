"""설정의 상대 좌표를 프레임 절대 좌표로 바꿉니다. 추출기, 보정 스크립트, 테스트가 함께 씁니다."""

from __future__ import annotations

Box = tuple[int, int, int, int]


def offset(box, dx: int, dy: int) -> Box:
    x, y, w, h = box
    return (x + dx, y + dy, w, h)


def slot_x(slots: dict, i: int) -> int:
    return slots["origin_x"] + i * slots["pitch_x"]


def slot_box(slots: dict, i: int, panel_y: int, rel_box) -> Box:
    """슬롯 i 패널(윗변 y = panel_y) 기준 상대 박스 → 절대 박스."""
    return offset(rel_box, slot_x(slots, i), panel_y)


def slot_field_box(slots: dict, i: int, panel_y: int, field: str) -> Box:
    return slot_box(slots, i, panel_y, slots["fields"][field]["box"])


def row_box(table: dict, i: int, box) -> Box:
    ox, oy = table["origin"]
    return offset(box, ox, oy + i * table["row_height"])

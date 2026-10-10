"""인게임 화면 추출: 라운드 번호, 슬롯별 TS/KS·팀명·전멸 여부, 우하단 누적 리더보드.

인게임 값은 임시값입니다. 리더보드는 직전 라운드까지의 누적이고 라운드 종료 때만 갱신됩니다.
"""

from __future__ import annotations

import re
from concurrent.futures import Executor
from functools import partial

import numpy as np

from .digits import Reader
from .frame import TemplateDetector, color_fraction, crop_box
from .layout import row_box, slot_anchor_box, slot_field_box
from .models import LeaderboardRow, SlotReading
from .runner import run_all
from .teams import TeamMatcher

CODE_WHITELIST = "ABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789"


def locate_panels(frame: np.ndarray, slots: dict) -> list[int]:
    """슬롯마다 패널 세로 위치를 후보 중에서 고릅니다. 관전 중인 팀 패널만 위로 올라옵니다."""
    anchor = slots["anchor"]

    def anchor_score(i: int, y: int) -> float:
        region = crop_box(frame, slot_anchor_box(slots, i, y))
        return color_fraction(region, anchor["hsv_low"], anchor["hsv_high"])

    return [max(slots["y_candidates"], key=partial(anchor_score, i)) for i in range(slots["count"])]


def number_fields(frame: np.ndarray, ig: dict, panel_ys: list[int]) -> dict[str, tuple[np.ndarray, str]]:
    """필드 키 → (크롭, 숫자 종류). 벤치마크도 이 함수로 같은 크롭을 얻습니다."""
    slots, lb = ig["slots"], ig["leaderboard"]
    fields = slots["fields"]
    out: dict[str, tuple[np.ndarray, str]] = {}
    for i, y in enumerate(panel_ys):
        for name in ("ts", "ks"):
            out[f"slot{i + 1}.{name}"] = (crop_box(frame, slot_field_box(slots, i, y, name)), fields[name]["kind"])
    for r in range(lb["rows"]):
        out[f"leaderboard{r + 1}.score"] = (crop_box(frame, row_box(lb, r, lb["score_box"])), lb["score_kind"])
    return out


def parse_round(text: str, pattern: str) -> int | None:
    m = re.search(pattern, text.upper())
    return int(m.group(1)) if m else None


def read_ingame(
    frame: np.ndarray,
    ig: dict,
    reader: Reader,
    matcher: TeamMatcher,
    skull: TemplateDetector,
    pool: Executor,
) -> tuple[int | None, list[SlotReading], list[LeaderboardRow]]:
    slots, lb = ig["slots"], ig["leaderboard"]
    panel_ys = locate_panels(frame, slots)

    tasks = {"round": partial(reader.read_text, crop_box(frame, ig["round_box"]))}
    for key, (img, kind) in number_fields(frame, ig, panel_ys).items():
        tasks[key] = partial(reader.read_number, img, kind)
    for i, y in enumerate(panel_ys):
        tasks[f"slot{i + 1}.name"] = partial(reader.read_text, crop_box(frame, slot_field_box(slots, i, y, "name")))
        tasks[f"slot{i + 1}.skull"] = partial(skull, crop_box(frame, slot_field_box(slots, i, y, "skull")))
    for r in range(lb["rows"]):
        code_img = crop_box(frame, row_box(lb, r, lb["code_box"]))
        tasks[f"leaderboard{r + 1}.code"] = partial(reader.read_text, code_img, 7, CODE_WHITELIST)
    out = run_all(pool, tasks)

    slot_readings = []
    for i, y in enumerate(panel_ys):
        p = f"slot{i + 1}"
        team_id, _ = matcher.match(out[f"{p}.name"])
        slot_readings.append(SlotReading(
            slot=i + 1, panel_y=y, team_id=team_id, team_raw=out[f"{p}.name"],
            ts=out[f"{p}.ts"], ks=out[f"{p}.ks"], eliminated=out[f"{p}.skull"],
        ))
    rows = []
    for r in range(lb["rows"]):
        p = f"leaderboard{r + 1}"
        team_id, _ = matcher.match(out[f"{p}.code"])
        rows.append(LeaderboardRow(rank=r + 1, team_id=team_id, team_raw=out[f"{p}.code"], score=out[f"{p}.score"]))
    return parse_round(out["round"], ig["round_pattern"]), slot_readings, rows

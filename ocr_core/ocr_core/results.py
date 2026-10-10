"""집계 화면 추출: 행(=순위)마다 팀명과 집계표 숫자. 집계 화면의 값은 확정값입니다."""

from __future__ import annotations

from concurrent.futures import Executor
from functools import partial

import numpy as np

from .digits import Reader
from .frame import crop_box
from .layout import row_box
from .models import ResultsRow
from .runner import run_all
from .teams import TeamMatcher


def number_fields(frame: np.ndarray, rc: dict) -> dict[str, tuple[np.ndarray, str]]:
    out: dict[str, tuple[np.ndarray, str]] = {}
    for r in range(rc["rows"]):
        for col in rc["columns"]:
            out[f"results{r + 1}.{col['name']}"] = (crop_box(frame, row_box(rc, r, col["box"])), col["kind"])
    return out


def read_results(
    frame: np.ndarray, rc: dict, reader: Reader, matcher: TeamMatcher, pool: Executor
) -> list[ResultsRow]:
    tasks = {key: partial(reader.read_number, img, kind) for key, (img, kind) in number_fields(frame, rc).items()}
    for r in range(rc["rows"]):
        tasks[f"results{r + 1}.name"] = partial(reader.read_text, crop_box(frame, row_box(rc, r, rc["name_box"])))
    out = run_all(pool, tasks)

    rows = []
    for r in range(rc["rows"]):
        p = f"results{r + 1}"
        team_id, _ = matcher.match(out[f"{p}.name"])
        values = {col["name"]: out[f"{p}.{col['name']}"] for col in rc["columns"]}
        rows.append(ResultsRow(rank=r + 1, team_id=team_id, team_raw=out[f"{p}.name"], values=values))
    return rows

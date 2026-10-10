"""합성 프레임으로 파이프라인 전체를 실제 tesseract 와 함께 돌립니다."""

import cv2
import numpy as np
import synth
from conftest import TEST_TEAMS, requires_tesseract

from ocr_core.frame import normalize
from ocr_core.ingame import locate_panels, split_values
from ocr_core.pipeline import OcrCore

SLOTS = [
    {"name": t["name_en"], "ts": ts, "ks": ks, "dead": ts == ks}
    for t, (ts, ks) in zip(TEST_TEAMS, [(5.0, 4.0), (3.0, 2.0), (0.0, 0.0), (12.5, 11.5), (1.0, 0.0), (7.0, 6.0), (2.0, 1.0), (9.0, 8.0)])
]
LEADERBOARD = [("NRG", 93), ("GIN", 75), ("JSD", 66), ("GBA", 48.5), ("BSX", 40), ("ICH", 31), ("DJN", 20), ("GWJ", 12)]


def skull(config):
    return cv2.imread(str(config.path(config.layout["ingame"]["slots"]["fields"]["skull"]["template"])), cv2.IMREAD_GRAYSCALE)


def test_split_values_takes_rightmost_groups():
    line = np.full((16, 140), 30, np.uint8)
    line[3:13, 0:4] = 200     # 왼쪽 잡음 (버려야 함)
    line[3:13, 30:40] = 130   # 회색 "TS" 라벨
    line[3:13, 50:70] = 240   # TS 값
    line[3:13, 80:95] = 130   # 회색 "KS" 라벨
    line[3:13, 100:112] = 240  # KS 값 (점 사이 틈 포함)
    line[3:13, 114:125] = 240
    ts, ks = split_values(line, 170, 5)
    assert ts.shape[1] == 20 + 6 and ks.shape[1] == 25 + 6  # 값 폭 + 좌우 여유 3px
    assert all(v.size == 0 for v in split_values(line[:, 90:], 170, 5, count=3))


def test_locate_panels_finds_raised_slot(config):
    img = synth.ingame_frame(config.layout, 3, SLOTS, LEADERBOARD, raised={2})
    ys = locate_panels(img, config.layout["ingame"]["slots"])
    normal, raised = config.layout["ingame"]["slots"]["y_candidates"]
    assert ys == [raised if i == 2 else normal for i in range(8)]


@requires_tesseract
def test_ingame_frame(config):
    img = synth.ingame_frame(config.layout, 3, SLOTS, LEADERBOARD, raised={2}, skull=skull(config))
    with OcrCore(config) as core:
        r = core.process(img)
    flat = r.flat()
    assert r.screen == "ingame"
    assert r.round == 3
    for i, s in enumerate(SLOTS, start=1):
        assert flat[f"slot{i}.ts"] == s["ts"], (i, r.slots[i - 1].ts)
        assert flat[f"slot{i}.ks"] == s["ks"], (i, r.slots[i - 1].ks)
        assert flat[f"slot{i}.team"] == TEST_TEAMS[i - 1]["id"], r.slots[i - 1].team_raw
        assert flat[f"slot{i}.eliminated"] == s["dead"], i
    for rank, (code, score) in enumerate(LEADERBOARD, start=1):
        assert flat[f"leaderboard{rank}.team"] == code
        assert flat[f"leaderboard{rank}.score"] == score
    assert r.review == []


@requires_tesseract
def test_results_frame_after_resize(config):
    rows = [(t["name_en"], {"total_fk": 10.0 - i, "total_points": 90.5 - 10 * i}) for i, t in enumerate(TEST_TEAMS)]
    img = synth.results_frame(config.layout, rows)
    small = cv2.resize(img, (1600, 900), interpolation=cv2.INTER_AREA)  # 다른 해상도 입력
    with OcrCore(config) as core:
        r = core.process(small)
    assert r.screen == "results"
    for rank, (name, values) in enumerate(rows, start=1):
        row = r.results[rank - 1]
        assert row.team_id == TEST_TEAMS[rank - 1]["id"], row.team_raw
        assert {k: v.value for k, v in row.values.items()} == values


def test_normalize_crop_removes_margins(config):
    img = synth.blank(config.layout)
    padded = cv2.copyMakeBorder(img, 0, 0, 100, 100, cv2.BORDER_CONSTANT, value=(0, 0, 0))
    out = normalize(padded, config.frame_size, crop=(100, 0, 1920, 1080))
    assert out.shape == (1080, 1920, 3)
    assert (out == img).all()

"""합성 프레임으로 파이프라인 전체를 실제 tesseract 와 함께 돌립니다."""

import cv2
import synth
from conftest import TEST_TEAMS, requires_tesseract

from ocr_core.frame import normalize
from ocr_core.ingame import locate_panels
from ocr_core.pipeline import OcrCore

SLOTS = [
    {"name": t["name_en"], "ts": ts, "ks": ks}
    for t, (ts, ks) in zip(TEST_TEAMS, [(5.0, 4.0), (3.0, 2.0), (0.0, 0.0), (12.5, 11.5), (1.0, 0.0), (7.0, 6.0), (2.0, 1.0), (9.0, 8.0)])
]
LEADERBOARD = [("NRG", 93), ("GIN", 75), ("JSD", 66), ("GBA", 48.5), ("BSX", 40), ("ICH", 31), ("DJN", 20), ("GWJ", 12)]


def test_locate_panels_finds_raised_slot(config):
    img = synth.ingame_frame(config.layout, 3, SLOTS, LEADERBOARD, raised={2})
    ys = locate_panels(img, config.layout["ingame"]["slots"])
    normal, raised = config.layout["ingame"]["slots"]["y_candidates"]
    assert ys == [raised if i == 2 else normal for i in range(8)]


@requires_tesseract
def test_ingame_frame(config):
    img = synth.ingame_frame(config.layout, 3, SLOTS, LEADERBOARD, raised={2})
    with OcrCore(config) as core:
        r = core.process(img)
    flat = r.flat()
    assert r.screen == "ingame"
    assert r.round == 3
    for i, s in enumerate(SLOTS, start=1):
        assert flat[f"slot{i}.ts"] == s["ts"], (i, r.slots[i - 1].ts)
        assert flat[f"slot{i}.ks"] == s["ks"], (i, r.slots[i - 1].ks)
        assert flat[f"slot{i}.team"] == TEST_TEAMS[i - 1]["id"], r.slots[i - 1].team_raw
    for rank, (code, score) in enumerate(LEADERBOARD, start=1):
        assert flat[f"leaderboard{rank}.team"] == code
        assert flat[f"leaderboard{rank}.score"] == score
    assert all(s.eliminated is None for s in r.slots)  # 해골 템플릿이 아직 없음


@requires_tesseract
def test_results_frame_after_resize(config):
    rows = [(t["name_en"], {"round_score": 10.0 - i, "total_score": 90.5 - 10 * i}) for i, t in enumerate(TEST_TEAMS)]
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

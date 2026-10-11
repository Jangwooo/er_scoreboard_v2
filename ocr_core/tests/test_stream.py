"""스트림 쪽 로직 테스트: 변경 추적, 참가팀 요청 검증, 소스 판별, ffmpeg 프레임 읽기."""

import shutil
import subprocess

import numpy as np
import pytest

from ocr_core.changes import ChangeTracker, format_changes
from ocr_core.models import FrameResult, NumberReading, SlotReading
from ocr_core.stream import FrameReader, Source, ffmpeg_command, is_youtube, resolve_source
from ocr_core.teams import TeamMatcher, teams_from_request


def reading(v):
    return NumberReading(v, str(v), 1.0 if v is not None else 0.0, "otsu_psm7_tight")


def ingame(ts: float | None, review=()):
    slot = SlotReading(slot=1, panel_y=0, team_id="GBA", team_raw="", ts=reading(ts), ks=reading(1.0), eliminated=False)
    return FrameResult(screen="ingame", screen_scores={}, round=3, slots=[slot], review=list(review))


def test_tracker_reports_only_changes():
    t = ChangeTracker()
    first = t.update(ingame(5.0))
    assert {c.key for c in first.changes} == {"screen", "round", "slot1.team", "slot1.eliminated", "slot1.ts", "slot1.ks"}
    assert not t.update(ingame(5.0))  # 같은 값이면 출력 없음
    changed = t.update(ingame(6.0), index=7, position=7.0)
    assert [(c.key, c.old, c.new) for c in changed.changes] == [("slot1.ts", 5.0, 6.0)]
    assert "slot1.ts  5.0 → 6.0" in format_changes(changed)


def test_tracker_keeps_last_value_on_review_and_other_screens():
    t = ChangeTracker()
    t.update(ingame(5.0))
    held = t.update(ingame(None, review=["slot1.ts"]))
    assert held.changes == [] and held.new_review == ["slot1.ts"]
    assert not t.update(ingame(None, review=["slot1.ts"]))  # 같은 review 는 다시 알리지 않음

    cam = t.update(FrameResult(screen="camera", screen_scores={}))
    assert [(c.key, c.new) for c in cam.changes] == [("screen", "camera")]
    back = t.update(ingame(5.0))  # 카메라 화면 동안 값을 지우지 않음 → 화면 전환만 변경
    assert [c.key for c in back.changes] == ["screen"]


def test_teams_from_request():
    teams = teams_from_request([{"code": "GBA", "names": ["경북 어센더스", "Gyeongbuk Ascension"]}, {"code": "NRG"}])
    m = TeamMatcher(teams)
    assert m.match("Gyeongbuk Ascen...")[0] == "GBA"
    assert m.match("경북 어센더스")[0] == "GBA"
    assert m.match("NRG")[0] == "NRG"


@pytest.mark.parametrize("bad", [None, [], [{"names": ["x"]}], [{"code": "A"}, {"code": "A"}], [{"code": "A", "names": "x"}]])
def test_teams_from_request_rejects(bad):
    with pytest.raises(ValueError):
        teams_from_request(bad)


def test_source_detection(tmp_path):
    assert is_youtube("https://www.youtube.com/watch?v=abc") and is_youtube("https://youtu.be/abc")
    assert not is_youtube("https://example.com/youtube.com")
    f = tmp_path / "vod.mp4"
    f.write_bytes(b"")
    assert resolve_source(str(f), "b") == Source(url=str(f), live=False)
    assert resolve_source("https://cdn.example.com/live.m3u8", "b").live


def test_ffmpeg_command_scales_to_frame_size():
    cmd = ffmpeg_command(Source(url="https://x/live.m3u8", live=True, headers={"User-Agent": "ua"}), 1, (1920, 1080))
    assert cmd[cmd.index("-vf") + 1] == "fps=1,scale=1920:1080"
    assert cmd[cmd.index("-headers") + 1] == "User-Agent: ua\r\n"
    assert "-headers" not in ffmpeg_command(Source(url="vod.mp4", live=False), 1, (1920, 1080))


@pytest.mark.skipif(shutil.which("ffmpeg") is None, reason="ffmpeg 가 설치되어 있지 않음")
def test_frame_reader_reads_every_frame_of_a_file(tmp_path):
    video = tmp_path / "v.mp4"
    subprocess.run(
        ["ffmpeg", "-loglevel", "error", "-f", "lavfi", "-i", "color=c=red:s=320x180:d=3:r=10", "-pix_fmt", "yuv420p", str(video)],
        check=True,
    )
    reader = FrameReader(Source(url=str(video), live=False), fps=2, size=(64, 36))
    try:
        frames = list(reader)
    finally:
        reader.close()
    assert [(i, p) for i, p, _ in frames] == [(i, i / 2) for i in range(6)]
    assert frames[0][2].shape == (36, 64, 3)
    assert np.all(frames[0][2][..., 2] > 200)  # BGR 의 R 채널
    assert reader.error is None

"""실제 중계 프레임 회귀 테스트. samples/labels.yaml 이 있을 때만 돌아갑니다."""

from pathlib import Path

import pytest
from conftest import requires_tesseract

from ocr_core.config import Config
from ocr_core.frame import load_image
from ocr_core.labels import load_labels
from ocr_core.pipeline import OcrCore

LABELS = Path(__file__).resolve().parent.parent / "samples" / "labels.yaml"
FRAMES = load_labels(LABELS) if LABELS.exists() else []


@pytest.fixture(scope="module")
def core():
    with OcrCore(Config.load()) as c:
        yield c


@requires_tesseract
@pytest.mark.skipif(not FRAMES, reason="samples/labels.yaml 없음")
@pytest.mark.parametrize("label", FRAMES, ids=[f.image.name for f in FRAMES])
def test_sample_frame(core, label):
    flat = core.process(load_image(label.image), label.crop).flat()
    wrong = {k: (exp, flat.get(k)) for k, exp in label.expected.items() if flat.get(k) != exp}
    assert not wrong, f"정답과 다른 필드 (정답, 읽음): {wrong}"

import re

import cv2
import numpy as np

from ocr_core.digits import FALLBACK, FAST, NumberKind, Reader, preprocess, tight_crop

DECIMAL = NumberKind(re.compile(r"\d{1,3}\.[05]"), 300)
SCORE = NumberKind(re.compile(r"\d{1,3}(\.5)?"), 500)


def test_decimal_kind_rejects_missing_point():
    assert DECIMAL.parse("48.5") == 48.5
    assert DECIMAL.parse("5.0") == 5.0
    assert DECIMAL.parse("485") is None  # 소수점이 빠진 오인식
    assert DECIMAL.parse("48.3") is None  # 0.5 단위가 아님
    assert DECIMAL.parse("") is None


def test_score_kind_range_and_format():
    assert SCORE.parse("93") == 93
    assert SCORE.parse("66.5") == 66.5
    assert SCORE.parse("9999") is None
    assert SCORE.parse("501") is None


def test_tight_crop_drops_border():
    img = np.zeros((40, 100), np.uint8)
    cv2.rectangle(img, (0, 0), (99, 39), 255, 1)  # 박스 테두리
    cv2.putText(img, "42", (30, 30), cv2.FONT_HERSHEY_SIMPLEX, 0.8, 255, 2)
    out = tight_crop(img)
    assert out.shape[0] < 40 and out.shape[1] < 100
    assert out[0, :].max() == 0 or out.shape[1] < 60  # 테두리 선이 남지 않음


def test_preprocess_makes_dark_text_on_white():
    img = np.full((30, 60, 3), 20, np.uint8)
    cv2.putText(img, "7", (20, 25), cv2.FONT_HERSHEY_SIMPLEX, 0.8, (255, 255, 255), 2)
    out = preprocess(img, FAST)
    assert np.count_nonzero(out == 255) > out.size / 2


class FakeOcr:
    """variant(psm, 크기)에 따라 정해 둔 문자열을 돌려줍니다."""

    def __init__(self, by_psm: dict[int, str]):
        self.by_psm = by_psm
        self.calls = 0

    def __call__(self, img, psm, whitelist):
        self.calls += 1
        return self.by_psm.get(psm, "")


def crop():
    rng = np.random.default_rng(0)
    return rng.integers(0, 255, (30, 60, 3), dtype=np.uint8)


def test_fast_path_and_cache():
    ocr = FakeOcr({7: "12.5"})
    reader = Reader(ocr, {"decimal": DECIMAL})
    img = crop()
    first = reader.read_number(img, "decimal")
    assert (first.value, first.confidence, first.variant) == (12.5, 1.0, FAST.name)
    reader.read_number(img.copy(), "decimal")  # 바이트가 같으면 캐시
    assert ocr.calls == 1


def test_fallback_majority_uses_psm13():
    # psm 7 은 형식 위반, psm 13 만 읽힘 → 다수결 (psm 13 변형 2개가 같은 값)
    reader = Reader(FakeOcr({7: "60", 13: "60.0"}), {"decimal": DECIMAL})
    r = reader.read_number(crop(), "decimal")
    psm13 = sum(v.psm == 13 for v in FALLBACK)
    assert r.value == 60.0
    assert r.variant == "majority"
    assert r.confidence == psm13 / len(FALLBACK)


def test_unreadable_returns_none():
    reader = Reader(FakeOcr({}), {"decimal": DECIMAL})
    r = reader.read_number(crop(), "decimal")
    assert r.value is None and r.confidence == 0.0

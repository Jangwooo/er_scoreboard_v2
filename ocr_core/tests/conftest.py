import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(Path(__file__).resolve().parent))

from ocr_core.config import Config  # noqa: E402
from ocr_core.digits import Tesseract  # noqa: E402

requires_tesseract = pytest.mark.skipif(not Tesseract.available(), reason="tesseract 가 설치되어 있지 않음")

TEST_TEAMS = [
    {"id": "GBA", "code": "GBA", "name_en": "Gyeongbuk Ascension", "name_ko": "", "aliases": []},
    {"id": "NRG", "code": "NRG", "name_en": "Energy Seoul", "name_ko": "", "aliases": []},
    {"id": "GIN", "code": "GIN", "name_en": "Ginkgo", "name_ko": "", "aliases": []},
    {"id": "JSD", "code": "JSD", "name_en": "Jeju Sundial", "name_ko": "", "aliases": []},
    {"id": "BSX", "code": "BSX", "name_en": "Busan Storm", "name_ko": "", "aliases": []},
    {"id": "ICH", "code": "ICH", "name_en": "Incheon Harbor", "name_ko": "", "aliases": []},
    {"id": "DJN", "code": "DJN", "name_en": "Daejeon Nova", "name_ko": "", "aliases": []},
    {"id": "GWJ", "code": "GWJ", "name_en": "Gwangju Light", "name_ko": "", "aliases": []},
]


@pytest.fixture
def config() -> Config:
    """기본 layout.yaml + 테스트용 가상 팀 표 (실제 참가팀 아님)."""
    cfg = Config.load()
    return Config(base_dir=cfg.base_dir, layout=cfg.layout, teams=TEST_TEAMS)

"""프레임 한 장 → 화면 분류 → 화면별 추출 → 검토 필요 필드 표시."""

from __future__ import annotations

import time
from concurrent.futures import ThreadPoolExecutor

import numpy as np

from .classifier import ScreenClassifier
from .config import Config
from .digits import OcrFn, Reader, Tesseract
from .frame import Box, TemplateDetector, normalize
from .ingame import read_ingame
from .models import FrameResult
from .results import read_results
from .teams import TeamMatcher


class OcrCore:
    def __init__(self, config: Config | None = None, ocr: OcrFn | None = None, workers: int | None = None):
        self.config = config or Config.load()
        layout = self.config.layout
        ocr_cfg = layout["ocr"]
        self.reader = Reader(ocr or Tesseract(**layout.get("tesseract", {})), self.config.number_kinds(), ocr_cfg["cache_size"])
        self.matcher = TeamMatcher(self.config.teams, layout["teams"]["min_score"])
        self.classifier = ScreenClassifier(layout["classifier"], self.config.base_dir)
        skull = layout["ingame"]["slots"]["fields"]["skull"]
        self.skull = TemplateDetector(self.config.path(skull["template"]), skull["threshold"])
        self.min_confidence = ocr_cfg["min_confidence"]
        self.pool = ThreadPoolExecutor(workers or ocr_cfg["workers"])

    def close(self) -> None:
        self.pool.shutdown()

    def __enter__(self) -> OcrCore:
        return self

    def __exit__(self, *exc) -> None:
        self.close()

    def process(self, img: np.ndarray, crop: Box | None = None) -> FrameResult:
        started = time.perf_counter()
        frame = normalize(img, self.config.frame_size, crop)
        screen, scores = self.classifier.classify(frame)
        result = FrameResult(screen=screen, screen_scores=scores, warnings=list(self.classifier.warnings))
        if not self.config.calibrated:
            result.warnings.append("layout.yaml 좌표가 아직 보정되지 않았습니다 (calibrated: false)")

        layout = self.config.layout
        if screen == "ingame":
            if self.skull.template is None:
                result.warnings.append(f"전멸 표시 템플릿이 없어 eliminated 는 null 입니다: {self.skull.path}")
            result.round, result.slots, result.leaderboard = read_ingame(
                frame, layout["ingame"], self.reader, self.matcher, self.skull, self.pool
            )
        elif screen == "results":
            result.results = read_results(frame, layout["results"], self.reader, self.matcher, self.pool)

        result.review = self._review(result)
        result.elapsed_ms = (time.perf_counter() - started) * 1000
        return result

    def _review(self, result: FrameResult) -> list[str]:
        """자동 반영하면 안 되는 필드. 이 목록은 관리자 확인으로 넘깁니다."""
        keys = [k for k, r in result.numbers().items() if r.value is None or r.confidence < self.min_confidence]
        keys += [k for k, v in result.flat().items() if k.endswith(".team") and v is None]
        if result.screen == "ingame" and result.round is None:
            keys.append("round")
        return keys

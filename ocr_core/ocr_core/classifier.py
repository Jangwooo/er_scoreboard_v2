"""중계 화면 분류: 대기, 현장 카메라, 인게임, 집계."""

from __future__ import annotations

from pathlib import Path

import cv2
import numpy as np

from .frame import color_fraction, crop_box, template_score


class ScreenClassifier:
    def __init__(self, cfg: dict, base_dir: Path):
        self.min_score = cfg["min_score"]
        self.screens: dict[str, list[dict]] = {name: s["probes"] for name, s in cfg["screens"].items()}
        self.warnings: list[str] = []
        self._templates: dict[str, np.ndarray] = {}
        for name, probes in self.screens.items():
            for p in probes:
                if p["check"] == "template":
                    path = base_dir / p["template"]
                    tpl = cv2.imread(str(path), cv2.IMREAD_GRAYSCALE)
                    if tpl is None:
                        self.warnings.append(f"분류 템플릿 없음, 검사 생략: {name}.{p['name']} ({path})")
                    else:
                        self._templates[p["template"]] = tpl

    def _probe(self, frame: np.ndarray, p: dict) -> float | None:
        region = crop_box(frame, p["box"])
        if p["check"] == "color":
            return 1.0 if color_fraction(region, p["hsv_low"], p["hsv_high"]) >= p["min_fraction"] else 0.0
        if p["check"] == "template":
            tpl = self._templates.get(p["template"])
            if tpl is None:
                return None
            return 1.0 if template_score(region, tpl) >= p["threshold"] else 0.0
        raise ValueError(f"알 수 없는 probe check: {p['check']}")

    def classify(self, frame: np.ndarray) -> tuple[str, dict[str, float]]:
        """(화면 이름, 화면별 probe 통과 비율). 기준을 넘는 화면이 없으면 "unknown"."""
        scores: dict[str, float] = {}
        for name, probes in self.screens.items():
            results = [r for r in (self._probe(frame, p) for p in probes) if r is not None]
            scores[name] = sum(results) / len(results) if results else 0.0
        best = max(scores, key=scores.get, default=None)
        if best is None or scores[best] < self.min_score:
            return "unknown", scores
        return best, scores

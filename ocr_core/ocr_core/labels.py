"""정답 라벨 파일(samples/labels.yaml) 로드. 회귀 테스트와 벤치마크가 함께 씁니다."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

import yaml


@dataclass
class FrameLabel:
    image: Path
    crop: tuple[int, int, int, int] | None
    expected: dict[str, object]  # FrameResult.flat() 의 키 → 정답


def load_labels(path: str | Path) -> list[FrameLabel]:
    path = Path(path)
    data = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
    return [
        FrameLabel(
            image=path.parent / f["image"],
            crop=tuple(f["crop"]) if f.get("crop") else None,
            expected=f.get("expected") or {},
        )
        for f in data.get("frames") or []
    ]

"""YAML 설정 로드. 좌표·임계값·팀 표는 코드와 분리해 둡니다."""

from __future__ import annotations

import re
from dataclasses import dataclass
from pathlib import Path

import yaml

from .digits import NumberKind

DEFAULT_CONFIG_DIR = Path(__file__).resolve().parent.parent / "config"


@dataclass
class Config:
    base_dir: Path  # 템플릿 등 상대 경로의 기준
    layout: dict
    teams: list[dict]

    @classmethod
    def load(cls, config_dir: str | Path | None = None) -> Config:
        base = Path(config_dir) if config_dir else DEFAULT_CONFIG_DIR
        layout = yaml.safe_load((base / "layout.yaml").read_text(encoding="utf-8"))
        teams_file = base / "teams.yaml"
        teams = []
        if teams_file.exists():
            teams = yaml.safe_load(teams_file.read_text(encoding="utf-8")).get("teams") or []
        return cls(base_dir=base, layout=layout, teams=teams)

    @property
    def calibrated(self) -> bool:
        return bool(self.layout.get("calibrated", False))

    @property
    def frame_size(self) -> tuple[int, int]:
        f = self.layout["frame"]
        return f["width"], f["height"]

    def path(self, rel: str) -> Path:
        return self.base_dir / rel

    def number_kinds(self) -> dict[str, NumberKind]:
        return {
            name: NumberKind(pattern=re.compile(spec["pattern"]), max=float(spec["max"]))
            for name, spec in self.layout["number_kinds"].items()
        }

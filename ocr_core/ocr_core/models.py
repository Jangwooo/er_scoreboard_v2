"""OCR 코어가 내보내는 결과 구조."""

from __future__ import annotations

from dataclasses import asdict, dataclass, field


@dataclass(frozen=True)
class NumberReading:
    value: float | None
    text: str  # tesseract 원문 (다수결이면 변형별 결과를 | 로 이음)
    confidence: float
    variant: str | None  # 값을 낸 경로: 빠른 경로 이름, "majority", 또는 None


@dataclass
class SlotReading:
    slot: int  # 1~8, 화면 왼쪽부터
    panel_y: int
    team_id: str | None
    team_raw: str
    ts: NumberReading
    ks: NumberReading
    eliminated: bool | None  # 해골 템플릿이 없으면 None


@dataclass
class LeaderboardRow:
    rank: int
    team_id: str | None
    team_raw: str
    score: NumberReading


@dataclass
class ResultsRow:
    rank: int
    team_id: str | None
    team_raw: str
    values: dict[str, NumberReading]


@dataclass
class FrameResult:
    screen: str  # waiting | camera | ingame | results | unknown
    screen_scores: dict[str, float]
    round: int | None = None
    slots: list[SlotReading] = field(default_factory=list)
    leaderboard: list[LeaderboardRow] = field(default_factory=list)
    results: list[ResultsRow] = field(default_factory=list)
    review: list[str] = field(default_factory=list)  # 관리자 확인이 필요한 필드 키
    warnings: list[str] = field(default_factory=list)
    elapsed_ms: float = 0.0

    def numbers(self) -> dict[str, NumberReading]:
        """필드 키 → 숫자 읽기 결과."""
        out: dict[str, NumberReading] = {}
        for s in self.slots:
            out[f"slot{s.slot}.ts"] = s.ts
            out[f"slot{s.slot}.ks"] = s.ks
        for r in self.leaderboard:
            out[f"leaderboard{r.rank}.score"] = r.score
        for r in self.results:
            for name, reading in r.values.items():
                out[f"results{r.rank}.{name}"] = reading
        return out

    def flat(self) -> dict[str, object]:
        """필드 키 → 최종 값. 라벨 파일과 비교할 때 씁니다."""
        out: dict[str, object] = {"screen": self.screen}
        if self.screen == "ingame":
            out["round"] = self.round
        for s in self.slots:
            out[f"slot{s.slot}.team"] = s.team_id
            out[f"slot{s.slot}.eliminated"] = s.eliminated
        for r in self.leaderboard:
            out[f"leaderboard{r.rank}.team"] = r.team_id
        for r in self.results:
            out[f"results{r.rank}.team"] = r.team_id
        out.update({k: v.value for k, v in self.numbers().items()})
        return out

    def to_dict(self) -> dict:
        return asdict(self)

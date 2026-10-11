"""프레임 결과를 이전 값과 비교해 바뀐 필드만 골라냅니다.

아직 여러 프레임 다수결이 없어서, 한 프레임의 오인식도 변경으로 나옵니다(로드맵 4단계).
review 에 든 필드와 읽지 못한 필드(None)는 변경으로 보지 않고 마지막 값을 유지합니다.
"""

from __future__ import annotations

from dataclasses import dataclass, field

from .models import FrameResult

READ_SCREENS = ("ingame", "results")


@dataclass(frozen=True)
class Change:
    key: str
    old: object
    new: object


@dataclass
class FrameChanges:
    index: int  # 스트림 시작부터 몇 번째로 읽은 프레임인지
    position: float  # 스트림 안의 위치(초)
    result: FrameResult
    changes: list[Change] = field(default_factory=list)
    new_review: list[str] = field(default_factory=list)  # 이번 프레임에 새로 검토 대상이 된 필드

    def __bool__(self) -> bool:
        return bool(self.changes or self.new_review)


class ChangeTracker:
    def __init__(self) -> None:
        self.values: dict[str, object] = {}  # 필드 키 → 마지막으로 확인한 값
        self.screen: str | None = None
        self._review: set[str] = set()

    def update(self, result: FrameResult, index: int = 0, position: float = 0.0) -> FrameChanges:
        out = FrameChanges(index=index, position=position, result=result)
        if result.screen != self.screen:
            out.changes.append(Change("screen", self.screen, result.screen))
            self.screen = result.screen
        if result.screen not in READ_SCREENS:
            return out  # 대기·현장 카메라 화면: 마지막 값을 그대로 유지

        review = set(result.review)
        for key, value in result.flat().items():
            if key == "screen" or value is None or key in review:
                continue
            if self.values.get(key) != value:
                out.changes.append(Change(key, self.values.get(key), value))
                self.values[key] = value
        out.new_review = sorted(review - self._review)
        self._review = review
        return out


def _fmt(value: object) -> str:
    return "-" if value is None else str(value)


def format_changes(fc: FrameChanges) -> str:
    """콘솔 출력용. 프레임 머리줄 + 바뀐 필드마다 한 줄."""
    r = fc.result
    m, s = divmod(int(fc.position), 60)
    h, m = divmod(m, 60)
    head = f"[{h:02d}:{m:02d}:{s:02d}] #{fc.index} {r.screen}"
    if r.screen == "ingame" and r.round is not None:
        head += f" R{r.round}"
    head += f" ({r.elapsed_ms:.0f} ms)"
    width = max((len(c.key) for c in fc.changes), default=0)
    lines = [head]
    lines += [f"  {c.key:<{width}}  {_fmt(c.old)} → {_fmt(c.new)}" for c in fc.changes]
    if fc.new_review:
        lines.append(f"  review: {', '.join(fc.new_review)}")
    return "\n".join(lines)

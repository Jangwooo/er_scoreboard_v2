"""팀 별칭 매칭. 한글 정식명, 잘린 영문 패널명, 3글자 코드를 같은 팀 id 로 모읍니다."""

from __future__ import annotations

import difflib
import re

_TRAILING_ELLIPSIS = re.compile(r"(\.{2,}|…)\s*$")


def normalize_name(text: str) -> str:
    text = _TRAILING_ELLIPSIS.sub("", text.strip())
    return "".join(ch for ch in text.upper() if ch.isalnum())


class TeamMatcher:
    def __init__(self, teams: list[dict], min_score: float = 0.6):
        self.min_score = min_score
        self._keys: dict[str, str] = {}  # 정규화된 표기 → 팀 id
        for team in teams:
            names = [team.get("id"), team.get("code"), team.get("name_en"), team.get("name_ko"), *(team.get("aliases") or [])]
            for name in names:
                key = normalize_name(str(name or ""))
                if key:
                    self._keys[key] = team["id"]

    def match(self, raw: str) -> tuple[str | None, float]:
        """(팀 id, 유사도). 맞는 팀이 없으면 (None, 최고 유사도)."""
        key = normalize_name(raw)
        if not key:
            return None, 0.0
        if key in self._keys:
            return self._keys[key], 1.0

        # 잘린 패널명: "Gyeongbuk Ascen..." → 앞부분이 같은 팀이 하나뿐이면 그 팀
        if len(key) >= 4:
            prefixed = {tid for k, tid in self._keys.items() if k.startswith(key)}
            if len(prefixed) == 1:
                return prefixed.pop(), 0.95

        best_id, best = None, 0.0
        for k, tid in self._keys.items():
            score = difflib.SequenceMatcher(None, key, k).ratio()
            if score > best:
                best_id, best = tid, score
        return (best_id, best) if best >= self.min_score else (None, best)

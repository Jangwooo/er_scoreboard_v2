"""팀 별칭 매칭. 한글 정식명, 잘린 영문 패널명, 3글자 코드를 같은 팀 id 로 모읍니다."""

from __future__ import annotations

import difflib
import re

_TRAILING_ELLIPSIS = re.compile(r"(\.{2,}|…)\s*$")


def normalize_name(text: str) -> str:
    text = _TRAILING_ELLIPSIS.sub("", text.strip())
    return "".join(ch for ch in text.upper() if ch.isalnum())


def teams_from_request(items: object) -> list[dict]:
    """백엔드가 보낸 참가팀 목록을 TeamMatcher 형식으로 바꿉니다.

    입력: [{"code": "GBA", "names": ["경북 어센더스", "Gyeongbuk Ascension"]}, ...]
    code 가 팀 id 가 되고, names 의 모든 표기(한글명, 영문명 등)가 별칭이 됩니다.
    """
    if not isinstance(items, list) or not items:
        raise ValueError("teams 는 비어 있지 않은 배열이어야 합니다")
    teams, seen = [], set()
    for item in items:
        if not isinstance(item, dict) or not isinstance(item.get("code"), str) or not item["code"].strip():
            raise ValueError(f"팀마다 문자열 code 가 필요합니다: {item!r}")
        code = item["code"].strip()
        names = item.get("names") or []
        if not isinstance(names, list) or not all(isinstance(n, str) for n in names):
            raise ValueError(f"names 는 문자열 배열이어야 합니다: {code}")
        if code in seen:
            raise ValueError(f"code 가 중복됩니다: {code}")
        seen.add(code)
        teams.append({"id": code, "code": code, "aliases": [n for n in names if n.strip()]})
    return teams


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

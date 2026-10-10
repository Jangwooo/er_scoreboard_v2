"""숫자·텍스트 읽기.

빠른 경로: 타이트 크롭 → 4배 확대 → Otsu 이진화 → tesseract psm 7.
빠른 경로의 결과가 형식 검증에 실패하면 psm 13 을 포함한 변형들로 다수결합니다.
같은 바이트의 크롭은 캐시에서 바로 돌려줍니다.
"""

from __future__ import annotations

import hashlib
import os
import re
import shutil
import subprocess
import threading
from collections import Counter, OrderedDict
from dataclasses import dataclass
from typing import Callable

import cv2
import numpy as np

from .frame import to_gray
from .models import NumberReading

DIGIT_WHITELIST = "0123456789."

# (전처리된 이미지, psm, whitelist) → 인식 문자열
OcrFn = Callable[[np.ndarray, int, str | None], str]


@dataclass(frozen=True)
class Variant:
    name: str
    psm: int = 7
    scale: int = 4
    otsu: bool = True
    tight: bool = True


FAST = Variant("otsu_psm7_tight")
FALLBACK = (
    Variant("otsu_psm13_tight", psm=13),  # 굵은 글자는 psm 13 에서만 읽히는 경우가 있음
    Variant("otsu_psm7_x8", scale=8),
    Variant("otsu_psm13_x8", psm=13, scale=8),
    Variant("otsu_psm7_loose", tight=False),
)
# 벤치마크에서 비교하는 변형 전체. 비-Otsu 는 가장 불안정해 비교용으로만 둠
BENCHMARK_VARIANTS = (Variant("fixed_psm7_loose", otsu=False, tight=False), FAST, *FALLBACK)


@dataclass(frozen=True)
class NumberKind:
    pattern: re.Pattern
    max: float

    def parse(self, text: str) -> float | None:
        """형식(소수점 유무 등)과 범위를 검증합니다. 48.5 → 485 같은 오인식을 여기서 거릅니다."""
        t = text.replace(" ", "").replace(",", ".").strip()
        if not self.pattern.fullmatch(t):
            return None
        value = float(t)
        return value if value <= self.max else None


class Tesseract:
    """tesseract CLI 호출. 이미지는 stdin 으로 넘겨 임시 파일을 만들지 않습니다."""

    def __init__(self, cmd: str = "tesseract", lang: str = "eng", timeout: float = 10.0):
        self.cmd = cmd
        self.lang = lang
        self.timeout = timeout
        # 필드를 스레드로 병렬 처리하므로 tesseract 내부 멀티스레드는 끔
        self._env = {**os.environ, "OMP_THREAD_LIMIT": "1"}

    @staticmethod
    def available(cmd: str = "tesseract") -> bool:
        return shutil.which(cmd) is not None

    def __call__(self, img: np.ndarray, psm: int, whitelist: str | None = None) -> str:
        ok, buf = cv2.imencode(".png", img)
        if not ok:
            return ""
        args = [self.cmd, "stdin", "stdout", "-l", self.lang, "--psm", str(psm)]
        if whitelist:
            args += ["-c", f"tessedit_char_whitelist={whitelist}"]
        r = subprocess.run(args, input=buf.tobytes(), capture_output=True, timeout=self.timeout, env=self._env)
        return r.stdout.decode("utf-8", "replace").strip()


def _foreground_mask(gray: np.ndarray) -> np.ndarray:
    _, mask = cv2.threshold(gray, 0, 255, cv2.THRESH_BINARY + cv2.THRESH_OTSU)
    if np.count_nonzero(mask) > mask.size / 2:  # 글자를 소수 클래스로 봄
        mask = cv2.bitwise_not(mask)
    return mask


def tight_crop(gray: np.ndarray, pad: int = 3) -> np.ndarray:
    """글자에만 맞춰 자릅니다. 박스 가장자리에 닿은 성분(테두리, 이웃 칸)은 버립니다.

    주변 여백과 테두리가 임계값과 인식을 흔들어 5.5 가 9.5 로 읽히던 문제를 막습니다.
    """
    if gray.size == 0:
        return gray
    mask = _foreground_mask(gray)
    n, _, stats, _ = cv2.connectedComponentsWithStats(mask, connectivity=8)
    h, w = mask.shape
    x0, y0, x1, y1 = w, h, 0, 0
    for i in range(1, n):
        x, y, cw, ch, area = stats[i]
        if x == 0 or y == 0 or x + cw >= w or y + ch >= h or area < 2:
            continue
        x0, y0, x1, y1 = min(x0, x), min(y0, y), max(x1, x + cw), max(y1, y + ch)
    if x1 <= x0 or y1 <= y0:
        return gray
    return gray[max(0, y0 - pad):min(h, y1 + pad), max(0, x0 - pad):min(w, x1 + pad)]


def preprocess(img: np.ndarray, variant: Variant) -> np.ndarray:
    """흰 배경에 검은 글자인 이진 이미지로 만듭니다."""
    gray = to_gray(img)
    if variant.tight:
        gray = tight_crop(gray)
    gray = cv2.resize(gray, None, fx=variant.scale, fy=variant.scale, interpolation=cv2.INTER_CUBIC)
    flag = cv2.THRESH_BINARY + (cv2.THRESH_OTSU if variant.otsu else 0)
    _, binary = cv2.threshold(gray, 127, 255, flag)
    if np.count_nonzero(binary) < binary.size / 2:  # 밝은 글자 → 반전
        binary = cv2.bitwise_not(binary)
    return cv2.copyMakeBorder(binary, 10, 10, 10, 10, cv2.BORDER_CONSTANT, value=255)


class _LRU:
    def __init__(self, size: int):
        self.size = size
        self.data: OrderedDict = OrderedDict()
        self.lock = threading.Lock()

    def get(self, key):
        with self.lock:
            if key not in self.data:
                return None
            self.data.move_to_end(key)
            return self.data[key]

    def put(self, key, value) -> None:
        with self.lock:
            self.data[key] = value
            self.data.move_to_end(key)
            if len(self.data) > self.size:
                self.data.popitem(last=False)


def _key(img: np.ndarray, tag: str) -> str:
    h = hashlib.sha1(np.ascontiguousarray(img).tobytes())
    h.update(f"{img.shape}|{tag}".encode())
    return h.hexdigest()


class Reader:
    def __init__(self, ocr: OcrFn, kinds: dict[str, NumberKind], cache_size: int = 4096):
        self.ocr = ocr
        self.kinds = kinds
        self._cache = _LRU(cache_size)

    def read_variant(self, img: np.ndarray, kind: str, variant: Variant) -> tuple[float | None, str]:
        text = self.ocr(preprocess(img, variant), variant.psm, DIGIT_WHITELIST)
        return self.kinds[kind].parse(text), text

    def read_number(self, img: np.ndarray, kind: str) -> NumberReading:
        key = _key(img, f"num:{kind}")
        cached = self._cache.get(key)
        if cached is None:
            cached = self._read_number(img, kind)
            self._cache.put(key, cached)
        return cached

    def _read_number(self, img: np.ndarray, kind: str) -> NumberReading:
        if img.size == 0:
            return NumberReading(None, "", 0.0, None)
        value, text = self.read_variant(img, kind, FAST)
        if value is not None:
            return NumberReading(value, text, 1.0, FAST.name)

        texts = [text]
        votes: Counter[float] = Counter()
        for variant in FALLBACK:
            v, t = self.read_variant(img, kind, variant)
            texts.append(t)
            if v is not None:
                votes[v] += 1
        joined = "|".join(texts)
        ranked = votes.most_common(2)
        if not ranked or (len(ranked) == 2 and ranked[0][1] == ranked[1][1]):
            return NumberReading(None, joined, 0.0, None)  # 읽지 못했거나 동률이면 확정하지 않음
        value, count = ranked[0]
        return NumberReading(value, joined, count / len(FALLBACK), "majority")

    def read_text(self, img: np.ndarray, psm: int = 7, whitelist: str | None = None, scale: int = 3) -> str:
        if img.size == 0:
            return ""
        key = _key(img, f"text:{psm}:{whitelist}:{scale}")
        cached = self._cache.get(key)
        if cached is None:
            variant = Variant("text", psm=psm, scale=scale, tight=False)
            cached = self.ocr(preprocess(img, variant), psm, whitelist)
            self._cache.put(key, cached)
        return cached

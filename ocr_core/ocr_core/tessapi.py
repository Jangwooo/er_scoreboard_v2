"""libtesseract C API 를 ctypes 로 직접 부릅니다.

tesseract CLI 는 호출마다 프로세스를 띄우고 언어 모델을 다시 읽어서 느립니다.
여기서는 스레드마다 엔진을 하나씩 만들어 OcrCore 가 닫힐 때(=스트림이 끝날 때)까지 계속 씁니다.
빌드가 필요한 바인딩(tesserocr) 대신 ctypes 를 써서 tesseract-ocr 패키지만 있으면 됩니다.
ctypes 는 C 함수를 부르는 동안 GIL 을 풀어 주므로 스레드끼리 실제로 병렬로 돕니다.
"""

from __future__ import annotations

import ctypes
import ctypes.util
import os
import threading

import numpy as np

_LIB_NAMES = ("libtesseract.so.5", "libtesseract.so", "libtesseract.5.dylib", "libtesseract.dylib")


def _load_lib() -> ctypes.CDLL | None:
    # 필드를 스레드로 병렬 처리하므로 tesseract 내부 멀티스레드는 끔. 라이브러리를 읽기 전에 설정해야 함
    os.environ.setdefault("OMP_THREAD_LIMIT", "1")
    names = [n for n in (ctypes.util.find_library("tesseract"),) if n] + list(_LIB_NAMES)
    for name in names:
        try:
            lib = ctypes.CDLL(name)
        except OSError:
            continue
        _declare(lib)
        return lib
    return None


def _declare(lib: ctypes.CDLL) -> None:
    p, c, i = ctypes.c_void_p, ctypes.c_char_p, ctypes.c_int
    sigs = {
        "TessBaseAPICreate": ([], p),
        "TessBaseAPIInit3": ([p, c, c], i),
        "TessBaseAPISetPageSegMode": ([p, i], None),
        "TessBaseAPISetVariable": ([p, c, c], i),
        "TessBaseAPISetImage": ([p, c, i, i, i, i], None),
        "TessBaseAPIGetUTF8Text": ([p], ctypes.POINTER(ctypes.c_char)),
        "TessDeleteText": ([ctypes.POINTER(ctypes.c_char)], None),
        "TessBaseAPIClear": ([p], None),
        "TessBaseAPIEnd": ([p], None),
        "TessBaseAPIDelete": ([p], None),
    }
    for name, (args, res) in sigs.items():
        fn = getattr(lib, name)
        fn.argtypes, fn.restype = args, res


_lib: ctypes.CDLL | None = None
_lib_loaded = False
_lib_lock = threading.Lock()


def library() -> ctypes.CDLL | None:
    global _lib, _lib_loaded
    with _lib_lock:
        if not _lib_loaded:
            _lib, _lib_loaded = _load_lib(), True
        return _lib


class _Engine:
    """TessBaseAPI 하나. 스레드 하나에서만 씁니다."""

    def __init__(self, lib: ctypes.CDLL, lang: str):
        self.lib = lib
        self.handle = lib.TessBaseAPICreate()
        if lib.TessBaseAPIInit3(self.handle, None, lang.encode()) != 0:
            lib.TessBaseAPIDelete(self.handle)
            raise RuntimeError(f"tesseract 초기화 실패 (lang={lang})")

    def recognize(self, img: np.ndarray, psm: int, whitelist: str | None) -> str:
        lib, h = self.lib, self.handle
        gray = np.ascontiguousarray(img, dtype=np.uint8)
        if gray.ndim != 2:
            raise ValueError("회색조 이미지만 받습니다")
        lib.TessBaseAPISetPageSegMode(h, psm)
        # 빈 whitelist 는 제한 없음. 이전 호출의 whitelist 가 남지 않도록 매번 설정
        lib.TessBaseAPISetVariable(h, b"tessedit_char_whitelist", (whitelist or "").encode())
        rows, cols = gray.shape
        lib.TessBaseAPISetImage(h, gray.ctypes.data_as(ctypes.c_char_p), cols, rows, 1, gray.strides[0])
        ptr = lib.TessBaseAPIGetUTF8Text(h)
        try:
            text = ctypes.string_at(ptr).decode("utf-8", "replace") if ptr else ""
        finally:
            if ptr:
                lib.TessDeleteText(ptr)
            lib.TessBaseAPIClear(h)
        return text.strip()

    def close(self) -> None:
        self.lib.TessBaseAPIEnd(self.handle)
        self.lib.TessBaseAPIDelete(self.handle)


class TesseractLib:
    """OcrFn 구현. 처음 부른 스레드마다 엔진을 만들고, close() 할 때까지 재사용합니다."""

    def __init__(self, lang: str = "eng", **_ignored):
        lib = library()
        if lib is None:
            raise RuntimeError("libtesseract 를 찾을 수 없습니다")
        self.lib = lib
        self.lang = lang
        self._local = threading.local()
        self._engines: list[_Engine] = []
        self._lock = threading.Lock()

    @staticmethod
    def available() -> bool:
        return library() is not None

    @property
    def engine_count(self) -> int:
        return len(self._engines)

    def _engine(self) -> _Engine:
        engine = getattr(self._local, "engine", None)
        if engine is None:
            engine = _Engine(self.lib, self.lang)
            self._local.engine = engine
            with self._lock:
                self._engines.append(engine)
        return engine

    def __call__(self, img: np.ndarray, psm: int, whitelist: str | None = None) -> str:
        return self._engine().recognize(img, psm, whitelist)

    def close(self) -> None:
        """엔진을 모두 해제합니다. 엔진을 쓰는 스레드가 모두 끝난 뒤에 부르세요."""
        with self._lock:
            engines, self._engines = self._engines, []
        for engine in engines:
            engine.close()

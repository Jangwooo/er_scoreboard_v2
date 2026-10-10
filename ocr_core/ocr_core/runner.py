"""필드 읽기를 스레드 풀에서 병렬로 실행합니다. tesseract 는 별도 프로세스라 GIL 영향이 없습니다."""

from __future__ import annotations

from concurrent.futures import Executor
from typing import Callable


def run_all(pool: Executor, tasks: dict[str, Callable[[], object]]) -> dict[str, object]:
    futures = {key: pool.submit(fn) for key, fn in tasks.items()}
    return {key: f.result() for key, f in futures.items()}

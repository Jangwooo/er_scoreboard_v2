"""정답을 아는 숫자 칸으로 전처리 변형별 정확도를 잽니다.

    python scripts/benchmark.py samples/labels.yaml

변형마다 단독으로 읽었을 때의 정답 수와, 실제 파이프라인(빠른 경로 + 다수결)의 정답 수를 출력합니다.
"""

from __future__ import annotations

import argparse
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from ocr_core import ingame, results  # noqa: E402
from ocr_core.config import Config  # noqa: E402
from ocr_core.digits import BENCHMARK_VARIANTS, Reader, make_tesseract  # noqa: E402
from ocr_core.frame import load_image, normalize  # noqa: E402
from ocr_core.labels import load_labels  # noqa: E402


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("labels")
    parser.add_argument("--config")
    args = parser.parse_args()

    cfg = Config.load(args.config)
    L = cfg.layout
    ocr, warning = make_tesseract(L.get("tesseract", {}))
    if warning:
        print(warning)
    reader = Reader(ocr, cfg.number_kinds(), cache_size=0)

    cases = []  # (필드 키, 크롭, 종류, 정답)
    for frame_label in load_labels(args.labels):
        frame = normalize(load_image(frame_label.image), cfg.frame_size, frame_label.crop)
        fields = {
            **ingame.number_fields(frame, L["ingame"], ingame.locate_panels(frame, L["ingame"]["slots"])),
            **results.number_fields(frame, L["results"]),
        }
        for key, expected in frame_label.expected.items():
            if key in fields:
                img, kind = fields[key]
                cases.append((f"{frame_label.image.name}:{key}", img, kind, float(expected)))
    if not cases:
        print("라벨에 숫자 칸이 없습니다.")
        return 1

    print(f"정답을 아는 숫자 {len(cases)}개\n")
    print(f"{'방식':<24}{'정답 수':>8}{'시간(초)':>10}")
    for variant in BENCHMARK_VARIANTS:
        started = time.perf_counter()
        correct = sum(reader.read_variant(img, kind, variant)[0] == exp for _, img, kind, exp in cases)
        print(f"{variant.name:<24}{correct:>8}{time.perf_counter() - started:>10.1f}")

    started = time.perf_counter()
    misses = []
    for key, img, kind, exp in cases:
        got = reader.read_number(img, kind)
        if got.value != exp:
            misses.append(f"  {key}: 정답 {exp}, 읽음 {got.value} ({got.text!r})")
    print(f"{'pipeline':<24}{len(cases) - len(misses):>8}{time.perf_counter() - started:>10.1f}")
    if misses:
        print("\n파이프라인 오답:")
        print("\n".join(misses))
    return 0


if __name__ == "__main__":
    sys.exit(main())

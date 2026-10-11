# AGENTS.md — OCR core

Guidance for working in `ocr_core/`. The plan, tournament rules, broadcast screens, shared contracts and conventions live in the [root AGENTS.md](../AGENTS.md); read that first. This file only covers what is specific to the OCR core.

## Input

- The live input stream is **1920×1080**. This is the native coordinate space of `config/layout.yaml`, so stream frames need no crop or resize.
- `--crop` exists only for the phone screenshots in `samples/` (3120×1440, video area `280,0,2560,1440`). Do not build the live path around it.

## Setup

```bash
cd ocr_core
sudo apt install tesseract-ocr ffmpeg  # system dependencies (libtesseract comes with tesseract-ocr)
python3 -m venv .venv && . .venv/bin/activate
pip install -e '.[dev]'
```

## Common commands

Run everything from `ocr_core/`.

```bash
pytest                                                   # full test suite (needs tesseract)
python -m ocr_core frame.png --pretty                    # read one 1920x1080 frame
python -m ocr_core shot.jpg --crop 280,0,2560,1440       # phone screenshot sample
python -m ocr_core stream <youtube-url|file> --teams teams.json   # read a stream, print changed values
python -m ocr_core serve --port 8100                     # HTTP API for the backend (see Stream API)
python scripts/draw_layout.py frame.png --out /tmp/overlay.png   # draw layout boxes for calibration
python scripts/benchmark.py samples/labels.yaml          # accuracy per preprocessing variant
```

## Stream API

The backend starts reading a stream with one HTTP request; only one match is read at a time.

```
POST   /streams  {"url": "https://www.youtube.com/watch?v=...",
                  "teams": [{"code": "GBA", "names": ["경북 어센더스", "Gyeongbuk Ascension"]}, ...]}
                 → 202 started / 400 bad request / 409 already reading
GET    /streams  → current (or last) session status: state, frames, dropped, last_ms, error
DELETE /streams  → stop
```

- `teams` comes from the backend, so the OCR core only does OCR. `code` becomes the team id; every entry in `names` (Korean name, English panel name, …) is an alias. `config/teams.yaml` is only the fallback for the single-frame CLI and the sample tests.
- YouTube links are resolved with yt-dlp; local files and other URLs go straight to ffmpeg. ffmpeg samples `stream.fps` frames per second (default 1) scaled to 1920×1080.
- Live input drops stale frames and always reads the newest one if OCR falls behind; files are read frame by frame without dropping.
- Changed values are printed to stdout per frame (`ocr_core/changes.py`). Fields in `review` or unreadable (`null`) never count as changes; the last value is kept. Waiting and camera screens only print the screen switch.
- The score event format sent to the backend is not defined yet; output is console only.

## Pipeline

1. **Normalize** to 1920×1080 (optional crop first, for samples only).
2. **Classify** the screen with fixed probes (color regions, templates) from `layout.yaml`.
3. **In-game extraction** (provisional): round number; per slot TS/KS, team name and elimination (skull template, threshold 0.80); bottom-right cumulative leaderboard. The "TS x KS y" line is right-aligned, so white values and grey labels are split by brightness and the two rightmost blobs are TS and KS.
4. **Results extraction** (final): team per rank and table values.
5. **Digit reading**: fast path = tight crop → 4× upscale → Otsu → tesseract psm 7. tesseract runs in-process through the libtesseract C API (`tessapi.py`, ctypes): each worker thread (`ocr.workers`, 4) creates one engine on first use and keeps it until `OcrCore.close()`, i.e. until the stream ends. `tesseract.backend: cli` switches back to one process per call. If format validation fails (e.g. decimal required, 0.5 steps), retry with 4 variants including psm 13 and take a majority vote. Identical crops are served from a byte cache. Low-confidence or unreadable fields go to `review`.
6. **Team matching**: Korean name, truncated English name and code all resolve to one id in `config/teams.yaml`.

| File | Role |
| --- | --- |
| `config/layout.yaml` | Coordinates, color ranges, thresholds, number formats |
| `config/teams.yaml` | Team alias table |
| `config/templates/skull.png` | Elimination template |
| `samples/` | Sample frames and ground truth `labels.yaml` |
| `ocr_core/frame.py` | Normalize, crop, color fraction, template matching |
| `ocr_core/classifier.py` | Screen classifier |
| `ocr_core/digits.py` | Digit/text reading, format validation, majority vote, cache |
| `ocr_core/tessapi.py` | libtesseract via ctypes; one long-lived engine per thread |
| `ocr_core/teams.py` | Team alias matching |
| `ocr_core/ingame.py`, `results.py` | In-game and results extractors |
| `ocr_core/runner.py` | Runs field reads in parallel on a thread pool |
| `ocr_core/pipeline.py` | `OcrCore`: full flow and review decisions |
| `ocr_core/labels.py` | Loads ground truth labels for tests and the benchmark |
| `ocr_core/stream.py` | Source resolution (yt-dlp), ffmpeg frame reader, `StreamSession` |
| `ocr_core/changes.py` | Compares frames and formats changed values for the console |
| `ocr_core/server.py` | HTTP API (`POST/GET/DELETE /streams`) |
| `ocr_core/cli.py` | Single-frame, `stream` and `serve` commands |
| `scripts/draw_layout.py` | Draws config boxes on a frame for calibration |
| `scripts/benchmark.py` | Accuracy per preprocessing variant against labels |

## Stage 1 results

On the 4 samples (waiting, camera, in-game, results) the screen type and every value matched ground truth: 16 TS/KS, 8 leaderboard, 16 results-table numbers, 8 team names, elimination marks and the round number.

Benchmark on the 40 known numbers:

| Method | Correct / 40 |
| --- | --- |
| No Otsu + psm 7 (4× scale) | 29 |
| Otsu + psm 7 (4–8× scale; scale barely matters) | 37 |
| Otsu + psm 7 + tight crop | 38 |
| Above + psm 13 fallback (full pipeline) | 40 |

- Tight cropping alone fixed a results-table 5.5 read as 9.5; margins and borders were throwing off thresholding and recognition.
- Fields that always have a decimal (TS/KS, results table) use format validation to reject misreads like 40.0 or 165.0.
- A bold "60" was only read by psm 13, which is why the fallback vote includes psm 13.
- No-Otsu was the least stable and often fell through to the slow path.

**Speed** (2 cores, after parallelizing): in-game 14.6 s → 7.6 s per frame, results 7.0 s → 3.8 s. Spawning a tesseract process per call dominates.

**Speed with in-process libtesseract** (8-core aarch64, same 4 samples, cache off): in-game 1.9 s → 0.1 s per frame, results 1.2 s → 0.08 s, versus the CLI backend on the same machine. Output is identical to the CLI on all 240 benchmark calls. The first frame takes a few hundred ms longer while the engines load.

**Stream check**: the 4 samples encoded as an H.264 video (1920×1080) and read through `stream` matched all 73 label values.

## Not implemented yet

- Not tested against a real YouTube live stream yet (only a local video built from the samples).
- No score event output to the backend; changed values only go to the console.
- No multi-frame voting or rule checks: a single-frame misread shows up as a change (roadmap step 4).
- No region-level change detection; every sampled frame is fully read (roadmap step 3).
- Digits are still read by tesseract; `matchTemplate` is only used for the skull mark.

## Known limitations

- Validated on only 4 phone screenshots; coordinates and thresholds were calibrated on those same 4.
- The result cache only hits on byte-identical crops; live video has compression noise, so the hit rate may be low.
- Teams NRG, GIN, JSD, BS: only the codes are confirmed; name mappings are guesses.
- The skull template comes from a single sample scene; the 0.80 threshold is untested at other resolutions or compression levels.

## Rules

The cross-component rules (doubtful values go to `review`, provisional vs final values, the `FrameResult.flat()` key contract) are in the root AGENTS.md under "Shared contracts". On top of those:

- **No coordinates, colors or thresholds in code.** They live in `config/layout.yaml` as `[x, y, w, h]` in 1920×1080 frame space. When the overlay changes (it can change per season or tournament), edit the config, not the code.
- Team names resolve to the id (3-letter code) in `config/teams.yaml`. Do not fill in code↔name mappings without evidence; mark guesses as guesses in a comment.

## Testing

- Run `pytest` after every change; everything must pass (37 tests today).
- In a fresh venv (OpenCV/numpy from pip), the two tests in `test_pipeline_synthetic.py` fail on the leaderboard code and a results value even before the stream change; with Debian's `python3-opencv` all pass. Not investigated yet.
- `tests/test_samples.py` is a regression test on real broadcast frames from `samples/labels.yaml`. If it fails, accuracy dropped: do not edit expected values to make it pass. Change a label only with evidence the label itself is wrong.
- When handling a new screen or tournament, add frames to `samples/` and their ground truth to `labels.yaml` (format in `labels.example.yaml`). Prefer real 1920×1080 stream frames over phone screenshots.
- Keep the logic tests (`test_digits.py`, `test_teams.py`, `test_classifier.py`) runnable without tesseract.
- For changes that affect speed, report processing time before and after.

## Recalibrating for a new overlay

1. Put real frames in `samples/`, at least one per screen type.
2. Draw the boxes: `python scripts/draw_layout.py samples/x.png --out /tmp/overlay.png`.
3. Fix coordinates and HSV ranges in `config/layout.yaml`; repeat step 2 until boxes line up.
4. If the elimination mark changed, crop it to `config/templates/skull.png`.
5. Update `config/teams.yaml` for the participating teams.
6. Add ground truth for the new frames to `samples/labels.yaml`.
7. Run `pytest` and `python scripts/benchmark.py samples/labels.yaml`.

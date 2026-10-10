# AGENTS.md

Guidance for coding agents working in this repository. Planning and design decisions live in the [planning doc](https://claude.ai/artifact/1ynZ9zs6cerWUBJaHLsnuh).

## Project

A service that reads Eternal Return esports YouTube broadcasts with OCR and shows each team's score and its advancement/win conditions in real time.

| Component | Stack | Status |
| --- | --- | --- |
| OCR core (`ocr_core/`) | Python 3.11+, OpenCV, tesseract, (planned) ffmpeg, yt-dlp | Stage 1 done |
| Main backend | FastAPI or Node, PostgreSQL, Redis, SSE | Not started |
| Frontend | Next.js (including an admin page) | Not started |

The OCR core is the only code so far. When starting the backend or frontend, create a separate top-level folder and add a section for it here.

## Input

- The live image stream arrives at **1920×1080**. This is the native coordinate space of `config/layout.yaml`, so stream frames need no crop or resize.
- `--crop` exists only for the phone screenshots in `samples/` (3120×1440, video area `280,0,2560,1440`). Do not build the live path around it.

## OCR core

See `ocr_core/README.md` for the processing flow and what each file does.

### Setup

```bash
cd ocr_core
sudo apt install tesseract-ocr        # system dependency
python3 -m venv .venv && . .venv/bin/activate
pip install -e '.[dev]'
```

### Common commands

Run everything from `ocr_core/`.

```bash
pytest                                                   # full test suite (needs tesseract)
python -m ocr_core frame.png --pretty                    # read one 1920x1080 frame
python -m ocr_core shot.jpg --crop 280,0,2560,1440       # phone screenshot sample
python scripts/draw_layout.py frame.png --out /tmp/overlay.png   # draw layout boxes for calibration
python scripts/benchmark.py samples/labels.yaml          # accuracy per preprocessing variant
```

### Rules

- **No coordinates, colors or thresholds in code.** They all live in `config/layout.yaml` as `[x, y, w, h]` in 1920×1080 frame space. When the broadcast overlay changes, edit the config, not the code.
- **Never auto-apply a doubtful value.** A field that could not be read, falls below `min_confidence`, or fails format validation goes into `review` for admin confirmation. Do not guess. Accuracy comes before speed.
- **In-game values are provisional; results-screen values are final.** Waiting and venue-camera screens are classified but not read, and the service keeps the last confirmed values.
- Team names resolve to the id (3-letter code) in `config/teams.yaml`. Do not fill in code↔name mappings without evidence; mark guesses as guesses in a comment.
- The result keys from `FrameResult.flat()` (`round`, `slotN.ts`, `leaderboardN.score`, …) are a contract shared with the label files and the future backend. If you change them, update `samples/labels.yaml`, the tests and the README together.

### Testing

- Run `pytest` after every change and make sure everything passes (26 tests today).
- `tests/test_samples.py` is a regression test on real broadcast frames from `samples/labels.yaml`. If it fails, accuracy dropped: do not edit the expected values to make it pass. Change a label only with evidence that the label itself is wrong.
- When handling a new screen or tournament, add frames to `samples/` and their ground truth to `labels.yaml` (format in `labels.example.yaml`). Prefer real 1920×1080 stream frames over phone screenshots.
- Keep the logic tests (`test_digits.py`, `test_teams.py`, `test_classifier.py`) runnable without tesseract.
- For changes that affect speed, report processing time before and after. One in-game frame currently takes about 7.6 s.

## Roadmap

Work in this order, per the planning doc:

1. Pull frames from VODs and grow the labeled set (ffmpeg, yt-dlp)
2. Replace tesseract with digit template matching (speed)
3. Change detection so unchanged regions are not re-read
4. Multi-frame majority voting and rule checks (scores never decrease, rounds increase in order)
5. Score engine (advancement and win conditions)

Unverified hypothesis: TS = kills + currently guaranteed placement points.

## Conventions

- Existing docs, code comments, docstrings and CLI help are in Korean; identifiers are in English. Follow the language of the file you are editing.
- Commit messages are in English: an imperative one-line subject, plus a body with the reason and verification results when needed.
- Commit on a feature branch, never directly on `main`.
- Only add large files such as sample images when they are needed.

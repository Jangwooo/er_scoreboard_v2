# AGENTS.md

Guidance for coding agents working in this repository. This file is the single source of truth for the plan, the rules of the game, shared contracts and the current state. Component details live in each component's own `AGENTS.md`. Keep it up to date when decisions change.

## Summary

- **Problem**: Eternal Return esports is broadcast on YouTube, but live scores are not shown per team in real time. Viewers have to work out for themselves how many points a team needs to reach the top 4 or win.
- **Goal**: Read score changes from the stream with OCR and show standings plus advancement/win conditions in real time.
- **Difficulty**: Medium overall. Most of the hard work is in the OCR core: one misread goes straight to every viewer, so stability matters more than anything.
- **Current state**: OCR core stage 1 works on 4 sample frames (screen classification, in-game and results extraction, all values correct). It is too slow for live use (~7.6 s per in-game frame).
- **Next**: Label frames from past VODs, then replace digit OCR with template matching.

## Architecture

```
YouTube stream ──URL──▶ OCR core ──score events──▶ Main backend ──SSE──▶ User frontend
                                                       │   ▲
                                                       ▼   │ manual adjustments
                                                     DB    Admin frontend
```

| Component | Responsibility | Stack | Difficulty | Status |
| --- | --- | --- | --- | --- |
| OCR core (`ocr_core/`) | Reads the stream, extracts and validates values, emits score changes | Python 3.11+, OpenCV, tesseract, ffmpeg, yt-dlp | Medium-high | Stage 1 done |
| Main backend | Creates tracked matches, passes the stream URL to the OCR core, applies score events, pushes to users | FastAPI (Python everywhere) or Node/TypeScript, PostgreSQL, Redis, SSE | Medium-low | Not started |
| Frontend | Users: live score page, past matches with per-round points. Admin: create matches to track, manual score adjustments during a match, other admin tasks | Next.js (React); admin pages in the same app behind auth | Low-medium | Not started |
| DB | Per-round results of past matches (matches, rounds, team scores) | PostgreSQL | Low | Not started |

- Decision: the OCR core takes a stream URL and reads the stream itself. The backend only hands over the URL and receives events. This is simpler than the backend relaying the stream.
- SSE, not WebSocket, for user push. Pushes go one way only.
- CPU only; no GPU needed.
- Deployment: Docker on a single VPS to start.
- When starting the backend or frontend, create a separate top-level folder with its own `AGENTS.md` (see Components).

## Tournament rules

The score engine must implement these. Keep rules in a config file, not in code, so they can change per tournament.

- **Round score** = placement points + kill points (1 kill = 1 point).
- **Placement points**: 1st 10, 2nd 7, 3rd 5, 4th 4, 5th 3, 6th 2, 7th 1, 8th 0 (from the results screen).
- A match is 4–9 rounds with 8 teams.
- **Advancement mode**: after round 4, the top 4 teams by total advance.
- **Checkpoint mode** (only in specific matches such as finals or LCQ): rounds 1–4 are played without checkpoints. From round 5, the top N teams by total *at the end of the previous round* hold a checkpoint mark:

  | Round | Teams holding a mark |
  | --- | --- |
  | 5 | 1 |
  | 6 | 3 |
  | 7 | 5 |
  | 8 | 7 |
  | 9 | 8 (all) |

  - Marks come from standings at the end of a round. A team that was 1st but gets overtaken loses its mark.
  - A team **wins** when it holds a mark and is the last team alive in the next round. The mark is not earned by adding that round's points.
- **Ties**: the team with more kill points ranks higher. A tie on kill points too has never happened and has no rule yet (open question).

### What the service shows

- **Provisional total** = cumulative total through the previous round + current round TS. The in-game leaderboard only updates at the end of a round, so this value is needed during a round. (TS meaning is still a hypothesis; see below.)
- **Advancement mode**: provisional standings and the points gap to the 4th-place cutoff.
- **Checkpoint mode**: which teams hold a mark this round and which of them are still alive, plus the gap to the mark cutoff for the next round. If every mark holder is eliminated, no one can win this round.

## Broadcast screens

The live stream is 1920×1080; input details are in [ocr_core/AGENTS.md](ocr_core/AGENTS.md).

There are 4 screen types. Only in-game and results carry scores. Waiting screens come before the match; then in-game and results alternate each round; the venue camera cuts in between at any time.

| Screen | How to recognize it | Use |
| --- | --- | --- |
| Waiting | White NEXT box top-left, top bar, team list on the right | Classify only. The team list can be used to validate teams |
| Venue camera | No HUD, logo and sponsor banner at the bottom | Ignore; keep last confirmed values |
| In-game | Top-right bar "KEL CIRCUIT n \| LOWER MATCH \| ROUND m", LEADERBOARD bottom-right | Read. **Provisional** values |
| Results | Large LEADERBOARD on the left, placement point table (10/7/5/4/3/2/1/0) | Read. **Final** values |

### What we know about the in-game screen

- Each team panel has a "TS 5.0 KS 4.0" line. KS = kill points. TS is believed to be kill points + currently guaranteed placement points, i.e. this round's score so far. Evidence: TS−KS was 1.0 for every surviving team and 0 only for the eliminated team. **Unverified; check against VODs.**
- The bottom-right LEADERBOARD (93, 75, 66, …) is the cumulative total through the previous round and only updates when a round ends (confirmed).
- The team panel slots (01–08, left to right) are fixed and not sorted by score. Only the spectated team's panel moves up (by 30 px), and its TS/KS line moves with it, so the vertical position is searched per slot.
- Team names appear in three forms: Korean full name (waiting), English panel name, sometimes truncated ("Gyeongbuk Ascen..."), and a 3-letter code (leaderboard). An alias table maps them to one id.
- Round labels vary (LOWER GROUP, MATCH, FINALS); only the ROUND number is used.
- Scores can end in .5, so a dropped decimal point is a common misread (48.5 → 485). Format validation catches this.

## Shared contracts

These hold across components. Each component's own AGENTS.md links here instead of repeating them.

- **Never auto-apply a doubtful value.** A field that could not be read, falls below `min_confidence`, or fails format validation goes into `review` for admin confirmation. Do not guess. Accuracy comes before speed. Manual adjustment in the admin page is the safety net.
- **In-game values are provisional; results-screen values are final.** Waiting and camera screens are classified but not read, and the service keeps the last confirmed values.
- **Result keys are a contract.** The keys from the OCR core's `FrameResult.flat()` (`round`, `slotN.ts`, `leaderboardN.score`, …) are shared with the label files and the future backend. If you change them, update `ocr_core/samples/labels.yaml`, the tests and the READMEs together.
- Team ids are the 3-letter codes in `ocr_core/config/teams.yaml`.
- The score event format (OCR core → backend) and the SSE payload (backend → frontend) are not defined yet. Define them here when they are, not in a component file.

## Components

Each component has its own `AGENTS.md` for setup, commands, file layout, component rules and testing. When you start the backend or frontend, create its top-level folder with a short `AGENTS.md` in the same shape and add a row here.

| Folder | Guide | Status |
| --- | --- | --- |
| `ocr_core/` | [ocr_core/AGENTS.md](ocr_core/AGENTS.md) | Stage 1 done: one frame is read correctly on 4 samples; no stream input, ~7.6 s per in-game frame |

## Roadmap

The most important thing now is measuring accuracy on real broadcast frames; 4 samples say nothing about a full broadcast.

1. **Label VOD frames**: collect frames from past VODs, label ground truth and extend the evaluation script. Verify the TS meaning (kills + guaranteed placement points) at the same time.
2. **Digit template matching**: digits use a fixed font, so replace tesseract with a template-matching classifier that reads in milliseconds. Keep tesseract for team names and labels only.
3. **Change detection** (tolerance-based): skip regions that did not change; read team names once per slot.
4. **Multi-frame voting and rule checks**: sample ~1 fps with ffmpeg and confirm values by majority across frames. Rules: scores never decrease, round numbers increase in order. On a violation, hold the value and alert the admin. Add VOD and live frame feeds (yt-dlp, ffmpeg).
5. **Score engine**: advancement/win conditions as pure logic with tests. It can be built and tested without OCR.

## Risks

- **YouTube terms and broadcast rights**: pulling and analyzing the stream server-side may break YouTube's terms. Ask Nimble Neuron (the game's developer) first.
- **Delay**: the broadcast runs an estimated 10–30 s behind the venue, so results could act as spoilers.
- **Layout changes**: overlays can change per season or tournament, which is why layout config is kept separate from code.

## Open questions

- [ ] How are teams ranked when kill points are also tied?
- [ ] Is TS really kills + currently guaranteed placement points?
- [ ] Has Nimble Neuron been asked whether server-side stream analysis is allowed?
- [ ] Where do we get past VODs (video files, or a few dozen frame captures)?

## Conventions

- Existing docs, code comments, docstrings and CLI help are in Korean; identifiers are in English. Follow the language of the file you are editing.
- Commit messages are in English: an imperative one-line subject, plus a body with the reason and verification results when needed.
- Commit on a feature branch, never directly on `main`.
- Only add large files such as sample images when they are needed.

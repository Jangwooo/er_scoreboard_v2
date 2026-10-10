# OCR 코어

이터널 리턴 e스포츠 중계 프레임에서 점수 정보를 읽는 모듈입니다. 프레임 한 장을 받아 화면 종류를 분류하고, 인게임 화면과 집계 화면에서 값을 읽어 JSON으로 돌려줍니다. 기획과 1단계 결과는 [기획 문서](https://claude.ai/artifact/1ynZ9zs6cerWUBJaHLsnuh)에 정리되어 있습니다.

> `config/layout.yaml`은 2026 KEL CIRCUIT 3 유튜브 중계 샘플 4장(대기, 현장 카메라, 인게임, 집계)으로 보정했습니다. 이 4장에서 화면 분류와 모든 값(숫자 40개, 팀 24개, 라운드, 전멸 표시)이 정답과 일치합니다. 검증한 프레임이 4장뿐이라 실제 방송 전체에서의 정확도는 아직 모릅니다.

## 설치

시스템에 `tesseract`가 있어야 합니다.

```bash
sudo apt install tesseract-ocr          # Debian/Ubuntu
python3 -m venv .venv && . .venv/bin/activate
pip install -e '.[dev]'
```

## 사용

```bash
python -m ocr_core frame.png --pretty
python -m ocr_core shot.jpg --crop 280,0,2560,1440   # 3120x1440 폰 스크린샷의 좌우 여백 제거
```

```python
from ocr_core import OcrCore
from ocr_core.frame import load_image

with OcrCore() as core:
    result = core.process(load_image("frame.png"))
    result.screen    # waiting | camera | ingame | results | unknown
    result.flat()    # {"round": 5, "slot1.ts": 5.0, "leaderboard1.score": 93, ...}
    result.review    # 자동 반영하면 안 되는 필드 → 관리자 확인으로
```

## 처리 흐름

1. **정규화**: (선택) crop 후 1920×1080으로 맞춥니다.
2. **화면 분류**: 화면마다 고정 요소(색상 영역, 템플릿)를 검사합니다. 대기와 현장 카메라 화면은 분류만 하고, 읽기는 하지 않습니다. 이때 서비스는 마지막 확정값을 유지합니다.
3. **인게임 추출**(임시값): 라운드 번호, 8개 슬롯의 TS/KS·팀명·전멸 표시, 우하단 누적 리더보드를 읽습니다.
   - 관전 중인 팀 패널만 30px 위로 올라옵니다. 팀 색 강조선은 팀마다 색이 달라서, 강조선과 바로 아래 패널의 밝기 차이가 큰 위치를 슬롯마다 고릅니다.
   - "TS 5.0 KS 4.0" 줄은 오른쪽 정렬이라 값 위치가 길이에 따라 바뀝니다. 흰 값과 회색 라벨을 밝기로 나눠 오른쪽 두 덩어리를 TS, KS로 읽습니다.
   - 전멸 표시는 초상화 위 해골 템플릿(`config/templates/skull.png`)으로 판정합니다. 샘플에서 해골은 0.98 이상, 해골이 없는 곳은 0.65 이하였습니다(임계값 0.80).
4. **집계 추출**(확정값): 순위별 팀명과 집계표 숫자를 읽습니다.
5. **숫자 읽기**: 숫자를 읽고 결과를 검증합니다.
   - 먼저 빠른 경로(타이트 크롭 → 4배 확대 → Otsu → tesseract psm 7)로 읽습니다.
   - 결과가 형식 검증(예: 소수점 필수, 0.5 단위)에 실패하면 psm 13을 포함한 4개 변형으로 다시 읽어 다수결합니다.
   - 같은 바이트의 크롭은 캐시에서 바로 돌려줍니다.
   - 신뢰도가 `min_confidence`보다 낮거나 읽지 못한 필드는 `review` 목록에 들어갑니다.
6. **팀 매칭**: 한글 정식명, 잘린 영문 패널명(`Gyeongbuk Ascen...`), 3글자 코드를 `config/teams.yaml`의 같은 팀 id로 모읍니다.

## 구성

| 파일 | 역할 |
| --- | --- |
| `config/layout.yaml` | 좌표, 색상 범위, 임계값, 숫자 형식 |
| `config/teams.yaml` | 팀 별칭 표 (CIRCUIT 3 샘플에서 옮김, 코드↔이름 대응 일부는 추정) |
| `config/templates/skull.png` | 전멸 표시 템플릿 |
| `samples/` | 샘플 프레임과 정답 라벨 `labels.yaml` |
| `ocr_core/frame.py` | 정규화, crop, 색상 비율, 템플릿 매칭 |
| `ocr_core/classifier.py` | 화면 분류기 |
| `ocr_core/digits.py` | 숫자·텍스트 읽기, 형식 검증, 다수결, 캐시 |
| `ocr_core/teams.py` | 팀 별칭 매칭 |
| `ocr_core/ingame.py`, `results.py` | 인게임·집계 추출기 |
| `ocr_core/pipeline.py` | `OcrCore`: 전체 흐름과 검토 필드 판정 |
| `scripts/draw_layout.py` | 설정 박스를 프레임 위에 그려 보정을 돕는 스크립트 |
| `scripts/benchmark.py` | 정답 라벨로 전처리 변형별 정확도를 재는 스크립트 |

## 좌표 보정

오버레이가 바뀌는 시즌이나 대회에는 다시 보정합니다.

1. 실제 중계 프레임을 `samples/`에 넣습니다. 대기, 현장 카메라, 인게임, 집계 화면을 화면별로 한 장 이상 넣으세요.
2. 박스를 그려 확인합니다.

   ```bash
   python scripts/draw_layout.py samples/ingame.jpg --crop 280,0,2560,1440 --out /tmp/overlay.png
   ```

3. `config/layout.yaml`의 좌표와 HSV 범위를 고치고, 박스가 맞을 때까지 2번을 반복합니다.
4. 전멸 표시가 바뀌었으면 해골을 잘라 `config/templates/skull.png`로 저장합니다.
5. `config/teams.yaml`을 참가팀에 맞게 고칩니다.
6. `samples/labels.yaml`에 새 프레임의 정답을 추가합니다(형식은 `labels.example.yaml`).
7. 테스트와 벤치마크를 돌립니다.

   ```bash
   pytest
   python scripts/benchmark.py samples/labels.yaml
   ```


## 테스트

```bash
pytest
```

- `test_digits.py`, `test_teams.py`, `test_classifier.py`: tesseract 없이 도는 로직 테스트입니다.
- `test_pipeline_synthetic.py`: 설정 좌표대로 그린 합성 프레임으로 파이프라인 전체를 tesseract와 함께 돌립니다. 실제 방송 정확도가 아니라, 구성 요소가 서로 맞물리는지를 확인합니다.
- `test_samples.py`: `samples/labels.yaml`의 실제 프레임으로 회귀 테스트를 합니다.

## 아직 하지 않은 것

기획 문서의 다음 단계에 해당하는 부분입니다.

- 스트림이나 VOD에서 프레임 가져오기 (ffmpeg, yt-dlp)
- 여러 프레임 다수결과 규칙 검증 (점수 감소 불가, 라운드 순차 증가)
- tesseract 대신 숫자 템플릿 매칭으로 속도 개선
- 변화 감지로 바뀌지 않은 영역 다시 읽지 않기
- TS가 "킬 + 현재 보장 순위 점수"라는 가설 검증

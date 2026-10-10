"""프레임 정규화와 공용 영상 처리 도구."""

from __future__ import annotations

from pathlib import Path

import cv2
import numpy as np

Box = tuple[int, int, int, int] | list[int]


def load_image(path: str | Path) -> np.ndarray:
    img = cv2.imread(str(path), cv2.IMREAD_COLOR)
    if img is None:
        raise FileNotFoundError(f"이미지를 읽을 수 없습니다: {path}")
    return img


def crop_box(img: np.ndarray, box: Box) -> np.ndarray:
    """프레임 밖으로 나간 부분은 잘라냅니다. 결과는 원본의 view 입니다."""
    x, y, w, h = (int(v) for v in box)
    H, W = img.shape[:2]
    x0, y0 = max(0, x), max(0, y)
    x1, y1 = min(W, x + w), min(H, y + h)
    return img[y0:max(y0, y1), x0:max(x0, x1)]


def normalize(img: np.ndarray, size: tuple[int, int], crop: Box | None = None) -> np.ndarray:
    """(선택) 여백 crop 후 기준 해상도로 맞춥니다. 폰 스크린샷은 좌우 여백을 crop 으로 제거합니다."""
    if crop is not None:
        img = crop_box(img, crop)
    if img.ndim == 2:
        img = cv2.cvtColor(img, cv2.COLOR_GRAY2BGR)
    if (img.shape[1], img.shape[0]) != tuple(size):
        shrinking = img.shape[1] > size[0]
        img = cv2.resize(img, tuple(size), interpolation=cv2.INTER_AREA if shrinking else cv2.INTER_CUBIC)
    return img


def to_gray(img: np.ndarray) -> np.ndarray:
    return img if img.ndim == 2 else cv2.cvtColor(img, cv2.COLOR_BGR2GRAY)


def color_fraction(img: np.ndarray, hsv_low, hsv_high) -> float:
    """HSV 범위에 드는 픽셀 비율."""
    if img.size == 0:
        return 0.0
    hsv = cv2.cvtColor(img, cv2.COLOR_BGR2HSV)
    mask = cv2.inRange(hsv, np.array(hsv_low, np.uint8), np.array(hsv_high, np.uint8))
    return float(np.count_nonzero(mask)) / mask.size


def template_score(img: np.ndarray, template: np.ndarray) -> float:
    """정규화 상관계수 최댓값. 영역이 템플릿보다 작으면 0."""
    gray = to_gray(img)
    if gray.shape[0] < template.shape[0] or gray.shape[1] < template.shape[1]:
        return 0.0
    res = cv2.matchTemplate(gray, template, cv2.TM_CCOEFF_NORMED)
    return float(res.max())


class TemplateDetector:
    """템플릿이 박스 안에 있는지 판정. 템플릿 파일이 없으면 항상 None."""

    def __init__(self, path: str | Path, threshold: float):
        self.path = Path(path)
        self.threshold = threshold
        self.template = cv2.imread(str(path), cv2.IMREAD_GRAYSCALE) if self.path.exists() else None

    def __call__(self, img: np.ndarray) -> bool | None:
        if self.template is None:
            return None
        return template_score(img, self.template) >= self.threshold

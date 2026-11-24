"""MOVAR - lightweight image quality gate before EUPE inference.

Checks only these three image-quality failure modes:
1. Low resolution (on ORIGINAL image, before 512x512 preprocessing)
2. Too dark (mean grayscale brightness / dark-pixel ratio)
3. Blurry (variance of Laplacian at consistent image size)

No scalp/skin classification or scalp exposure estimation is performed.
All user-facing validation failures return the same generic message.
Thresholds are STARTING POINTS and must be tuned on real MOVAR capture images.

Usage:
    pip install opencv-python numpy
    python image_validation.py /path/to/photo.jpg

In the inference endpoint:
    report = validate_image(image_bgr)
    if not report["passed"]:
        return {"success": False, "error_code": "INVALID_IMAGE", "message": report["message"]}
    # continue with EUPE image preprocessing and inference
"""

from __future__ import annotations

import argparse
import json
from dataclasses import dataclass
from pathlib import Path

import cv2
import numpy as np

ERROR_MESSAGE = "입력 오류입니다. 다시 확인하시고 업로드 부탁드립니다."


@dataclass(frozen=True)
class ValidationConfig:
    min_short_side: int = 512  # Original image; illustrative default
    min_mean_brightness: float = 55.0
    dark_pixel_cutoff: int = 35
    max_dark_pixel_fraction: float = 0.70
    blur_variance_min: float = 70.0
    blur_reference_long_side: int = 512


def load_image(image_path: str | Path) -> np.ndarray | None:
    """Open an image including paths containing Korean characters."""
    try:
        data = np.fromfile(str(image_path), dtype=np.uint8)
        if data.size == 0:
            return None
        return cv2.imdecode(data, cv2.IMREAD_COLOR)
    except (OSError, ValueError, cv2.error):
        return None


def _laplacian_variance(image_bgr: np.ndarray, reference_long_side: int) -> float:
    """Focus proxy. It is affected by hair texture and lighting."""
    height, width = image_bgr.shape[:2]
    ratio = reference_long_side / max(width, height)
    resized = cv2.resize(
        image_bgr,
        (max(1, round(width * ratio)), max(1, round(height * ratio))),
        interpolation=cv2.INTER_AREA if ratio < 1 else cv2.INTER_LINEAR,
    )
    gray = cv2.cvtColor(resized, cv2.COLOR_BGR2GRAY)
    return float(cv2.Laplacian(gray, cv2.CV_64F).var())


def validate_image(
    image_bgr: np.ndarray | None,
    *,
    cfg: ValidationConfig = ValidationConfig(),
) -> dict:
    """Validate an image. Only ALL PASS leads to EUPE inference.

    `checks` and `measurements` are useful for developer logs; display
    `message` to end users when `passed` is False.
    """
    checks = {"resolution": "not_checked", "brightness": "not_checked", "focus": "not_checked"}
    measurements: dict[str, float | int] = {}
    reasons: list[str] = []

    def failed(code: str) -> None:
        reasons.append(code)

    if (
        not isinstance(image_bgr, np.ndarray)
        or image_bgr.ndim != 3
        or image_bgr.shape[2] != 3
        or image_bgr.dtype != np.uint8
        or image_bgr.shape[0] == 0
        or image_bgr.shape[1] == 0
    ):
        return {
            "passed": False,
            "error_code": "INVALID_IMAGE",
            "message": ERROR_MESSAGE,
            "checks": checks,
            "reasons": ["UNREADABLE_IMAGE"],
            "measurements": measurements,
        }

    height, width = image_bgr.shape[:2]
    measurements.update(width=width, height=height)

    # 1. Resolution before preprocessing or interpolation.
    if min(width, height) < cfg.min_short_side:
        checks["resolution"] = "fail"
        failed("LOW_RESOLUTION")
    else:
        checks["resolution"] = "pass"

    # 2. Low exposure, not a diagnosis of whether a scalp is visible.
    gray = cv2.cvtColor(image_bgr, cv2.COLOR_BGR2GRAY)
    mean_brightness = float(gray.mean())
    dark_fraction = float((gray <= cfg.dark_pixel_cutoff).mean())
    measurements.update(
        mean_brightness=round(mean_brightness, 2),
        dark_pixel_fraction=round(dark_fraction, 4),
    )
    if mean_brightness < cfg.min_mean_brightness or dark_fraction > cfg.max_dark_pixel_fraction:
        checks["brightness"] = "fail"
        failed("TOO_DARK")
    else:
        checks["brightness"] = "pass"

    # 3. Blur proxy, computed at a consistent scale across resolutions.
    blur_score = _laplacian_variance(image_bgr, cfg.blur_reference_long_side)
    measurements["laplacian_variance"] = round(blur_score, 2)
    if blur_score < cfg.blur_variance_min:
        checks["focus"] = "fail"
        failed("BLURRY_IMAGE")
    else:
        checks["focus"] = "pass"

    passed = not reasons
    return {
        "passed": passed,
        "error_code": None if passed else "INVALID_IMAGE",
        "message": None if passed else ERROR_MESSAGE,
        "checks": checks,
        "reasons": reasons,  # For logs; do not expose as detailed user feedback.
        "measurements": measurements,
    }


def validate_path(image_path: str | Path, *, cfg: ValidationConfig = ValidationConfig()) -> dict:
    return validate_image(load_image(image_path), cfg=cfg)


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="MOVAR 이미지 품질 검사 (해상도, 어두움, 흐릿함)")
    parser.add_argument("image", help="검사할 이미지 파일 경로")
    args = parser.parse_args()
    print(json.dumps(validate_path(args.image), ensure_ascii=False, indent=2))

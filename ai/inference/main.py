"""MOVAR V7 inference API (FastAPI).

Run from the MOVAR project root:
    python3 -m uvicorn api.main:app --host 127.0.0.1 --port 8000

This API never trains the model and never writes submitted photographs to disk.
It deliberately imports the *exact* V7 validation preprocessor to avoid
training/serving skew.
"""

from __future__ import annotations

import io
import os
import threading
import time
from contextlib import asynccontextmanager, nullcontext
from pathlib import Path
from typing import Any

import numpy as np
import torch
from fastapi import FastAPI, File, HTTPException, Response, UploadFile
from fastapi.middleware.cors import CORSMiddleware
from PIL import Image, UnidentifiedImageError

# The file is installed at <project_root>/api/main.py.
PROJECT_ROOT = Path(__file__).resolve().parent.parent
CHECKPOINT_DEFAULT = (
    PROJECT_ROOT
    / "outputs/checkpoints/eupe_finetune_512_ratio_mild_v7/best.pt"
)
MAX_UPLOAD_BYTES = 10 * 1024 * 1024  # 10 MiB
MAX_IMAGE_PIXELS = 16_000_000
ALLOWED_FORMATS = {"JPEG", "PNG", "WEBP"}
LABEL_COLS = tuple(f"value_{i}" for i in range(1, 7))
SYMPTOM_NAMES = (
    "미세각질",
    "피지과다",
    "모낭사이홍반",
    "모낭홍반농포",
    "비듬",
    "탈모",
)
MODEL_VERSION = "MOVAR-EUPE-V7-512"

# These imports use the existing, tested MOVAR project source code.
from src.models.movar_eupe import MOVAREUPE  # noqa: E402
from scripts.finetune_eupe_v7 import make_transform  # noqa: E402


def get_checkpoint_path() -> Path:
    override = os.getenv("MOVAR_CHECKPOINT")
    if not override:
        return CHECKPOINT_DEFAULT
    selected = Path(override).expanduser()
    return selected if selected.is_absolute() else PROJECT_ROOT / selected


class InferenceEngine:
    def __init__(self) -> None:
        self.device = torch.device("cuda" if torch.cuda.is_available() else "cpu")
        self.bf16 = bool(
            self.device.type == "cuda" and torch.cuda.is_bf16_supported()
        )
        self.checkpoint_path = get_checkpoint_path()
        self.lock = threading.Lock()  # Serialize GPU requests to control VRAM use.

        if not self.checkpoint_path.is_file():
            raise FileNotFoundError(
                "V7 best.pt 파일을 찾지 못했습니다: " + str(self.checkpoint_path)
            )
        repo = PROJECT_ROOT / "third_party/EUPE"
        weights = PROJECT_ROOT / "weights/eupe/EUPE-ViT-S.pt"
        if not repo.is_dir():
            raise FileNotFoundError("EUPE 코드 폴더가 없습니다: " + str(repo))
        if not weights.is_file():
            raise FileNotFoundError("EUPE 사전학습 가중치가 없습니다: " + str(weights))

        checkpoint = torch.load(
            self.checkpoint_path, map_location="cpu", weights_only=True
        )
        if not isinstance(checkpoint, dict) or "model_state_dict" not in checkpoint:
            raise ValueError("V7 체크포인트에 model_state_dict가 없습니다.")
        checkpoint_size = checkpoint.get("image_size", 512)
        if isinstance(checkpoint_size, (list, tuple)):
            checkpoint_size = checkpoint_size[0]
        if int(checkpoint_size) != 512:
            raise ValueError(
                f"512 모델 체크포인트가 아닙니다: image_size={checkpoint_size}"
            )

        model = MOVAREUPE(
            repo_dir=repo,
            weights_path=weights,
            freeze_backbone=True,
        )
        model.load_state_dict(checkpoint["model_state_dict"], strict=True)
        model.to(self.device)
        model.eval()
        self.model = model
        self.val_macro_f1 = float(checkpoint.get("best_val_macro_f1", -1))
        self.epoch = checkpoint.get("epoch")

        # V7 original validation pipeline:
        # LongestMaxSize(512) -> PadIfNeeded(512, fill=0, center)
        # -> ImageNet Normalize -> ToTensorV2
        self.transform = make_transform(train=False)

    @torch.inference_mode()
    def predict(self, rgb_image: np.ndarray) -> list[dict[str, Any]]:
        tensor = self.transform(image=rgb_image)["image"].unsqueeze(0)
        tensor = tensor.to(self.device, non_blocking=self.device.type == "cuda")
        result: list[dict[str, Any]] = []
        with self.lock:
            amp_context = (
                torch.autocast(device_type="cuda", dtype=torch.bfloat16)
                if self.bf16
                else nullcontext()
            )
            with amp_context:
                outputs = self.model(tensor)
            for name, col in zip(SYMPTOM_NAMES, LABEL_COLS):
                logits = outputs[col]
                if logits.shape != (1, 4):
                    raise RuntimeError(f"{col} 출력 형태 오류: {tuple(logits.shape)}")
                scores = (
                    torch.softmax(logits.float(), dim=-1)[0]
                    .detach()
                    .cpu()
                    .tolist()
                )
                grade = int(np.argmax(scores))
                result.append(
                    {
                        "key": col,
                        "name": name,
                        "grade": grade,
                        "grade_label": f"{grade}단계",
                        "score": round(float(scores[grade]), 6),
                        "class_scores": {
                            str(i): round(float(score), 6)
                            for i, score in enumerate(scores)
                        },
                    }
                )
        return result


@asynccontextmanager
async def lifespan(app: FastAPI):
    engine = InferenceEngine()
    app.state.engine = engine
    print(
        f"[MOVAR API] Ready | device={engine.device} | "
        f"bf16={engine.bf16} | epoch={engine.epoch} | "
        f"val_macro_f1={engine.val_macro_f1:.6f}",
        flush=True,
    )
    try:
        yield
    finally:
        del app.state.engine
        if torch.cuda.is_available():
            torch.cuda.empty_cache()


app = FastAPI(
    title="MOVAR AI 두피 분석 API",
    description=(
        "EUPE-ViT-S/16 기반 연구·프로젝트용 6개 두피 증상 0~3단계 분류. "
        "의학적 진단이나 치료를 대체하지 않습니다."
    ),
    version="1.0.0",
    lifespan=lifespan,
)

# Local web app defaults. Set MOVAR_CORS_ORIGINS for other frontends.
origins = [
    part.strip()
    for part in os.getenv(
        "MOVAR_CORS_ORIGINS",
        "http://localhost:3000,http://127.0.0.1:3000,"
        "http://localhost:5173,http://127.0.0.1:5173",
    ).split(",")
    if part.strip()
]
app.add_middleware(
    CORSMiddleware,
    allow_origins=origins,
    allow_credentials=False,
    allow_methods=["GET", "POST"],
    allow_headers=["Content-Type"],
)


@app.get("/")
def index() -> dict[str, str]:
    return {
        "service": "MOVAR AI 두피 분석 API",
        "version": MODEL_VERSION,
        "docs": "/docs",
        "health": "/health",
    }


@app.get("/health")
def health() -> dict[str, Any]:
    engine = app.state.engine
    return {
        "status": "ok",
        "model": MODEL_VERSION,
        "device": engine.device.type,
        "bf16": engine.bf16,
        "input_size": [512, 512],
        "checkpoint_epoch": engine.epoch,
        "checkpoint_val_macro_f1": (
            engine.val_macro_f1 if engine.val_macro_f1 >= 0 else None
        ),
    }


@app.post("/predict")
def predict(response: Response, file: UploadFile = File(...)) -> dict[str, Any]:
    """Accept an image, return six heads' grades and uncalibrated scores."""
    if file.content_type and not (
        file.content_type.startswith("image/")
        or file.content_type == "application/octet-stream"
    ):
        raise HTTPException(status_code=415, detail="이미지 파일만 업로드할 수 있습니다.")

    content = file.file.read(MAX_UPLOAD_BYTES + 1)
    if not content:
        raise HTTPException(status_code=400, detail="비어 있는 파일입니다.")
    if len(content) > MAX_UPLOAD_BYTES:
        raise HTTPException(status_code=413, detail="이미지는 10MB 이하만 허용됩니다.")

    try:
        with Image.open(io.BytesIO(content)) as image:
            if image.format not in ALLOWED_FORMATS:
                raise HTTPException(
                    status_code=415, detail="JPEG, PNG, WEBP 이미지만 지원합니다."
                )
            width, height = image.size
            if width * height > MAX_IMAGE_PIXELS:
                raise HTTPException(status_code=413, detail="이미지 해상도가 너무 큽니다.")
            if min(width, height) < 64:
                raise HTTPException(status_code=400, detail="이미지가 너무 작습니다.")
            # Same conversion as the V7 validation dataset. Images are not stored.
            rgb_image = np.asarray(image.convert("RGB"))
    except HTTPException:
        raise
    except (UnidentifiedImageError, OSError, ValueError, Image.DecompressionBombError):
        raise HTTPException(status_code=400, detail="이미지 파일을 해석할 수 없습니다.")

    engine: InferenceEngine = app.state.engine
    start = time.perf_counter()
    predictions = engine.predict(rgb_image)
    latency_ms = round((time.perf_counter() - start) * 1000, 2)
    response.headers["Cache-Control"] = "no-store"
    return {
        "model": MODEL_VERSION,
        "input": {"width": width, "height": height},
        "inference_size": {"width": 512, "height": 512},
        "symptoms": predictions,
        "inference_time_ms": latency_ms,
        "notice": (
            "AI 분석 결과는 연구·참고용이며 의료진의 진단을 대체하지 않습니다. "
            "class_scores는 보정된 의학적 확률이 아닙니다. 배고프다."
        ),
    }

"""MOVAR V7 - EUPE-ViT-S/16, 512x512, aspect-ratio preserving.

프로젝트 루트에서:
  python3 scripts/finetune_eupe_v7_512.py --check-only
  python3 scripts/finetune_eupe_v7_512.py

기존 데이터/체크포인트를 수정하지 않으며, Test split은 사용하지 않습니다.
기준 V6: Focal(gamma=2), AdamW, blocks 8~11, 2x oversampling, Cosine.
V7에서 달라지는 요소: 512 입력, 비율 유지 전처리, 약한 증강.
"""

import argparse
import csv
import json
import os
import random
import sys
import time
from pathlib import Path

import albumentations as A
import cv2
import numpy as np
import torch
import torch.nn as nn
import torch.nn.functional as F
from albumentations.pytorch import ToTensorV2
from PIL import Image
from sklearn.metrics import f1_score, precision_score, recall_score
from torch.utils.data import DataLoader, Dataset, WeightedRandomSampler

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from src.dataset import MOVARDataset, BASE as DATA_BASE
from src.models.movar_eupe import MOVAREUPE

SEED = 42
IMAGE_SIZE = 512
LABEL_COLS = [f"value_{i}" for i in range(1, 7)]
SYMPTOMS = ["미세각질", "피지과다", "모낭사이홍반", "모낭홍반농포", "비듬", "탈모"]
SAMPLING_WEIGHTS = [1.0, 2.0, 2.0, 2.0]  # value_4의 0/1/2/3단계


def set_seed(seed):
    random.seed(seed)
    np.random.seed(seed)
    torch.manual_seed(seed)
    torch.cuda.manual_seed_all(seed)


def make_transform(train):
    # 원본 640x480 -> 512x384(비율 유지) -> 여백을 더해 512x512.
    # 640x640 중간 변환 / 이미지 찌그러뜨리는 Resize(512,512) 없음.
    transforms = [
        A.LongestMaxSize(max_size=IMAGE_SIZE, interpolation=cv2.INTER_LINEAR),
        A.PadIfNeeded(
            min_height=IMAGE_SIZE,
            min_width=IMAGE_SIZE,
            border_mode=cv2.BORDER_CONSTANT,
            fill=(0, 0, 0),
            position="center",
        ),
    ]

    if train:
        # Albumentations 2.0.8 호환. 작은 병변을 가리는 CoarseDropout 제거.
        transforms += [
            A.HorizontalFlip(p=0.50),
            A.VerticalFlip(p=0.50),
            A.RandomRotate90(p=0.25),
            A.Rotate(
                limit=(-10, 10),
                interpolation=cv2.INTER_LINEAR,
                border_mode=cv2.BORDER_CONSTANT,
                fill=(0, 0, 0),
                p=0.20,
            ),
            A.OneOf(
                [
                    A.RandomBrightnessContrast(
                        brightness_limit=0.08, contrast_limit=0.08, p=1.0
                    ),
                    A.CLAHE(clip_limit=2.0, tile_grid_size=(8, 8), p=1.0),
                ],
                p=0.25,
            ),
        ]

    transforms += [
        A.Normalize(
            mean=(0.485, 0.456, 0.406),
            std=(0.229, 0.224, 0.225),
        ),
        ToTensorV2(),
    ]
    return A.Compose(transforms)


class ScalpDataset(Dataset):
    def __init__(self, csv_path, train):
        source = MOVARDataset(csv_path)
        self.image_paths = source.image_paths
        self.labels = source.labels
        self.transform = make_transform(train)

    def __len__(self):
        return len(self.image_paths)

    def __getitem__(self, index):
        path = DATA_BASE / self.image_paths[index]
        with Image.open(path) as img:
            rgb = np.asarray(img.convert("RGB"))
        image = self.transform(image=rgb)["image"]
        labels = torch.as_tensor(self.labels[index], dtype=torch.long)
        return image, labels


def make_sampler(dataset):
    values = np.asarray(dataset.labels[:, 3], dtype=np.int64)
    sample_weights = np.asarray(SAMPLING_WEIGHTS, dtype=np.float64)[values]
    return WeightedRandomSampler(
        weights=torch.from_numpy(sample_weights.copy()).double(),
        num_samples=len(dataset),
        replacement=True,
        generator=torch.Generator().manual_seed(SEED),
    )


class FocalLoss(nn.Module):
    """V6와 동일: alpha[class] * (1-pt)^2 * CE, 배치 평균."""

    def __init__(self, alpha, gamma=2.0):
        super().__init__()
        self.register_buffer("alpha", alpha.detach().clone())
        self.gamma = gamma

    def forward(self, logits, targets):
        ce = F.cross_entropy(logits.float(), targets, reduction="none")
        pt = torch.exp(-ce)
        return (self.alpha[targets] * (1.0 - pt).pow(self.gamma) * ce).mean()


def make_criterions(device):
    with (ROOT / "outputs/dataset/class_weights.json").open(encoding="utf-8") as f:
        weights = json.load(f)
    return {
        col: FocalLoss(
            alpha=torch.tensor(weights[col], dtype=torch.float32, device=device),
            gamma=2.0,
        )
        for col in LABEL_COLS
    }


def build_model(device):
    # V6와 동일한 초기 체크포인트. V6 best에서 '추가 학습'하는 것이 아님.
    model = MOVAREUPE(
        repo_dir=ROOT / "third_party/EUPE",
        weights_path=ROOT / "weights/eupe/EUPE-ViT-S.pt",
        freeze_backbone=True,
    )
    initial_path = ROOT / "outputs/checkpoints/eupe_linear_v1/best.pt"
    initial_ckpt = torch.load(initial_path, map_location="cpu", weights_only=True)
    model.load_state_dict(initial_ckpt["model_state_dict"], strict=True)

    for p in model.backbone.parameters():
        p.requires_grad = False
    for block in model.backbone.blocks[-4:]:
        for p in block.parameters():
            p.requires_grad = True
    for p in model.heads.parameters():
        p.requires_grad = True
    return model.to(device)


def make_optimizer(model):
    return torch.optim.AdamW(
        [
            {
                "params": [p for p in model.backbone.parameters() if p.requires_grad],
                "lr": 1e-5,
            },
            {
                "params": [p for p in model.heads.parameters() if p.requires_grad],
                "lr": 1e-4,
            },
        ],
        weight_decay=0.01,
    )


def total_focal_loss(outputs, labels, criterions):
    losses = [
        criterions[col](outputs[col], labels[:, i])
        for i, col in enumerate(LABEL_COLS)
    ]
    return torch.stack(losses).mean()


def set_train_mode(model):
    model.train()
    model.backbone.eval()  # 동결된 블록은 eval 유지
    for block in model.backbone.blocks[-4:]:
        block.train()


def train_one_epoch(model, loader, optimizer, criterions, device, amp, accum):
    set_train_mode(model)
    optimizer.zero_grad(set_to_none=True)
    params = [p for p in model.parameters() if p.requires_grad]
    steps = len(loader)
    total_loss, seen = 0.0, 0

    for step, (images, labels) in enumerate(loader, start=1):
        images = images.to(device, non_blocking=True)
        labels = labels.to(device, non_blocking=True)

        # 마지막 불완전한 accumulation 그룹도 올바르게 평균.
        group_start = ((step - 1) // accum) * accum + 1
        group_size = min(accum, steps - group_start + 1)
        with torch.autocast("cuda", dtype=torch.bfloat16, enabled=amp):
            outputs = model(images)
            loss = total_focal_loss(outputs, labels, criterions)
        (loss / group_size).backward()

        if step % accum == 0 or step == steps:
            torch.nn.utils.clip_grad_norm_(params, max_norm=1.0)
            optimizer.step()
            optimizer.zero_grad(set_to_none=True)

        total_loss += loss.item() * images.size(0)
        seen += images.size(0)
        if step % 500 == 0 or step == steps:
            print(f"Train Step {step:,}/{steps:,} | Focal Loss {loss.item():.4f}", flush=True)
    return total_loss / seen


@torch.inference_mode()
def validate(model, loader, device, amp):
    model.eval()
    criterion = nn.CrossEntropyLoss()  # V6와 동일한 Validation CE
    total_ce, seen = 0.0, 0
    preds, labels_all = [], []

    for images, labels in loader:
        images = images.to(device, non_blocking=True)
        labels = labels.to(device, non_blocking=True)
        with torch.autocast("cuda", dtype=torch.bfloat16, enabled=amp):
            outputs = model(images)
            ce = torch.stack(
                [criterion(outputs[col].float(), labels[:, i]) for i, col in enumerate(LABEL_COLS)]
            ).mean()
        total_ce += ce.item() * images.size(0)
        seen += images.size(0)
        pred = torch.stack([outputs[col].argmax(1) for col in LABEL_COLS], dim=1)
        preds.append(pred.cpu().numpy())
        labels_all.append(labels.cpu().numpy())

    y_pred = np.concatenate(preds)
    y_true = np.concatenate(labels_all)
    head_f1, recall3 = {}, {}
    for i, col in enumerate(LABEL_COLS):
        head_f1[col] = float(f1_score(
            y_true[:, i], y_pred[:, i], labels=[0, 1, 2, 3],
            average="macro", zero_division=0,
        ))
        recall3[col] = float(recall_score(
            y_true[:, i], y_pred[:, i], labels=[0, 1, 2, 3],
            average=None, zero_division=0,
        )[3])

    # 6개 증상 Macro F1 평균 + value_4의 오탐/미탐 점검
    i = 3
    p4 = precision_score(
        y_true[:, i], y_pred[:, i], labels=[0, 1, 2, 3],
        average=None, zero_division=0,
    )
    r4 = recall_score(
        y_true[:, i], y_pred[:, i], labels=[0, 1, 2, 3],
        average=None, zero_division=0,
    )
    value4_binary = {
        "precision": float(precision_score(y_true[:, i] > 0, y_pred[:, i] > 0, zero_division=0)),
        "recall": float(recall_score(y_true[:, i] > 0, y_pred[:, i] > 0, zero_division=0)),
        "f1": float(f1_score(y_true[:, i] > 0, y_pred[:, i] > 0, zero_division=0)),
    }
    value4_grades = {
        str(g): {"precision": float(p4[g]), "recall": float(r4[g])}
        for g in (1, 2, 3)
    }
    mean_f1 = float(np.mean(list(head_f1.values())))
    return total_ce / seen, mean_f1, head_f1, recall3, value4_grades, value4_binary


def check_only(model, train_loader, val_ds, criterions, device, amp):
    images, labels = next(iter(train_loader))
    assert tuple(images.shape[2:]) == (512, 512)
    val_image, _ = val_ds[0]
    assert tuple(val_image.shape[1:]) == (512, 512)
    print(f"[TEST] Train batch: {tuple(images.shape)}, Val image: {tuple(val_image.shape)}")
    set_train_mode(model)
    images, labels = images.to(device), labels.to(device)
    torch.cuda.reset_peak_memory_stats()
    with torch.autocast("cuda", dtype=torch.bfloat16, enabled=amp):
        loss = total_focal_loss(model(images), labels, criterions)
    loss.backward()
    opt = make_optimizer(model)
    torch.nn.utils.clip_grad_norm_([p for p in model.parameters() if p.requires_grad], 1.0)
    opt.step()
    opt.zero_grad(set_to_none=True)
    torch.cuda.synchronize()
    print(f"[TEST OK] Forward / Backward / AdamW | Loss {loss.item():.4f}")
    print(f"[TEST] PyTorch peak allocated: {torch.cuda.max_memory_allocated()/2**30:.2f} GiB")
    print(f"[TEST] PyTorch peak reserved:  {torch.cuda.max_memory_reserved()/2**30:.2f} GiB")
    print("[TEST] 체크포인트 및 데이터 파일 수정 없음")


def main():
    parser = argparse.ArgumentParser(description="MOVAR V7 512x512 Focal Fine-tuning")
    parser.add_argument("--epochs", type=int, default=30)
    parser.add_argument("--batch-size", type=int, default=4)
    parser.add_argument("--accumulation-steps", type=int, default=4)
    parser.add_argument("--num-workers", type=int, default=2)
    parser.add_argument("--patience", type=int, default=5)
    parser.add_argument("--run-name", default="eupe_finetune_512_ratio_mild_v7")
    parser.add_argument("--check-only", action="store_true")
    args = parser.parse_args()

    if min(args.epochs, args.batch_size, args.accumulation_steps, args.patience) < 1:
        parser.error("epochs, batch-size, accumulation-steps, patience는 1 이상이어야 합니다.")
    if args.num_workers < 0:
        parser.error("num-workers는 0 이상이어야 합니다.")
    if args.run_name in (".", "..") or Path(args.run_name).name != args.run_name:
        parser.error("run-name에는 폴더 이름만 입력하세요.")
    if not torch.cuda.is_available():
        raise RuntimeError("CUDA GPU가 없습니다.")

    output = ROOT / "outputs/checkpoints" / args.run_name
    if not args.check_only and output.exists():
        raise FileExistsError(f"기존 실험 결과 보호: {output}")

    set_seed(SEED)
    torch.set_float32_matmul_precision("high")
    device = torch.device("cuda")
    amp = torch.cuda.is_bf16_supported()

    print("=" * 64)
    print("MOVAR V7 | 512x512, Ratio Keep, Mild Aug, Focal Loss")
    print("=" * 64)
    print(f"GPU: {torch.cuda.get_device_name(0)} | BF16: {amp}")
    print(f"Batch: {args.batch_size} | Accum: {args.accumulation_steps} ")
    print(f"Effective Batch: {args.batch_size * args.accumulation_steps}")
    print("Backbone blocks 8~11 | AdamW | Cosine | Focal gamma=2")
    print("Oversampling: value_4 grades 1~3 x2")
    print("Train/Val: LongestMaxSize(512) -> PadIfNeeded(512)")
    print("Train augmentation: flip, rotation, mild light/CLAHE; NO CoarseDropout")
    print("Initial checkpoint: outputs/checkpoints/eupe_linear_v1/best.pt")

    train_ds = ScalpDataset(ROOT / "outputs/dataset/splits/train.csv", train=True)
    val_ds = ScalpDataset(ROOT / "outputs/dataset/splits/val.csv", train=False)
    print(f"Train: {len(train_ds):,} / Validation: {len(val_ds):,}")
    loader_cfg = dict(
        batch_size=args.batch_size,
        num_workers=args.num_workers,
        pin_memory=True,
        persistent_workers=args.num_workers > 0,
    )
    train_loader = DataLoader(train_ds, sampler=make_sampler(train_ds), **loader_cfg)
    val_loader = DataLoader(val_ds, shuffle=False, **loader_cfg)

    model = build_model(device)
    criterions = make_criterions(device)
    if args.check_only:
        check_only(model, train_loader, val_ds, criterions, device, amp)
        return

    output.mkdir(parents=True, exist_ok=False)
    optimizer = make_optimizer(model)
    scheduler = torch.optim.lr_scheduler.CosineAnnealingLR(
        optimizer, T_max=args.epochs, eta_min=1e-6
    )
    config = {
        "image_size": [512, 512],
        "preprocessing": "LongestMaxSize(512) + PadIfNeeded(512, fill=0, center)",
        "augmentation": "HorizontalFlip50,VerticalFlip50,Rotate90_25,Rotate10_20,LightOrCLAHE25",
        "model": "MOVAREUPE ViT-S/16",
        "initial_checkpoint": "outputs/checkpoints/eupe_linear_v1/best.pt",
        "finetuned_blocks": [8, 9, 10, 11],
        "loss": "alpha-weighted FocalLoss(gamma=2)",
        "optimizer": "AdamW(backbone_lr=1e-5,head_lr=1e-4,weight_decay=0.01)",
        "scheduler": "CosineAnnealingLR",
        "sampler": "WeightedRandomSampler value_4 [1,2,2,2]",
        "batch_size": args.batch_size,
        "accumulation_steps": args.accumulation_steps,
        "epochs": args.epochs,
        "early_stopping_patience": args.patience,
        "seed": SEED,
    }
    (output / "config.json").write_text(
        json.dumps(config, ensure_ascii=False, indent=2), encoding="utf-8"
    )

    best_f1, best_epoch, stale = -1.0, 0, 0
    history = []
    start = time.perf_counter()
    for epoch in range(1, args.epochs + 1):
        t0 = time.perf_counter()
        print("\n" + "=" * 64)
        print(f"MOVAR V7 Epoch {epoch}/{args.epochs}", flush=True)
        train_focal = train_one_epoch(
            model, train_loader, optimizer, criterions,
            device, amp, args.accumulation_steps,
        )
        val_ce, f1, heads, rec3, grade4, binary4 = validate(
            model, val_loader, device, amp
        )
        scheduler.step()
        torch.cuda.synchronize()
        duration = (time.perf_counter() - t0) / 60

        print(f"Train Focal: {train_focal:.4f} | Val CE: {val_ce:.4f}")
        print(f"Val Mean Macro F1: {f1:.6f} | Time: {duration:.1f}min")
        for col, symptom in zip(LABEL_COLS, SYMPTOMS):
            print(f"  {symptom:<9} F1={heads[col]:.4f} | Recall(3)={rec3[col]:.4f}")
        print(
            "value_4 Recall(1/2/3): "
            + "/".join(f"{grade4[str(g)]['recall']:.4f}" for g in (1, 2, 3))
        )
        print(
            "value_4 Precision(1/2/3): "
            + "/".join(f"{grade4[str(g)]['precision']:.4f}" for g in (1, 2, 3))
        )
        print(
            f"value_4 Binary Presence P={binary4['precision']:.4f} "
            f"R={binary4['recall']:.4f} F1={binary4['f1']:.4f}"
        )

        if f1 > best_f1 + 1e-4:
            best_f1, best_epoch, stale = f1, epoch, 0
            ckpt = {
                "epoch": epoch,
                "model_state_dict": model.state_dict(),
                "best_val_macro_f1": best_f1,
                "head_f1": heads,
                "head_recall_3": rec3,
                "value_4_grades": grade4,
                "value_4_binary": binary4,
                "image_size": IMAGE_SIZE,
                "finetuned_blocks": [8, 9, 10, 11],
                "loss_type": "FocalLoss",
                "focal_gamma": 2.0,
                "preprocessing": config["preprocessing"],
                "augmentation": config["augmentation"],
                "sampling_weights": SAMPLING_WEIGHTS,
            }
            # 저장 도중 중단되어도 이전 best.pt를 깨뜨리지 않도록 임시 파일 이용.
            temp_path = output / "best.pt.tmp"
            torch.save(ckpt, temp_path)
            os.replace(temp_path, output / "best.pt")
            print("★ V7 best.pt 저장")
        else:
            stale += 1
            print(f"개선 없음: {stale}/{args.patience}")

        row = {
            "epoch": epoch,
            "train_focal_loss": train_focal,
            "val_ce_loss": val_ce,
            "val_mean_macro_f1": f1,
            "epoch_minutes": duration,
        }
        for col in LABEL_COLS:
            row[f"{col}_f1"] = heads[col]
            row[f"{col}_recall_3"] = rec3[col]
        for grade in (1, 2, 3):
            row[f"value_4_precision_{grade}"] = grade4[str(grade)]["precision"]
            row[f"value_4_recall_{grade}"] = grade4[str(grade)]["recall"]
        row.update({f"value_4_binary_{k}": v for k, v in binary4.items()})
        history.append(row)
        history_path = output / "history.csv"
        with history_path.open("w", newline="", encoding="utf-8-sig") as f:
            writer = csv.DictWriter(f, fieldnames=history[0].keys())
            writer.writeheader()
            writer.writerows(history)

        if stale >= args.patience:
            print(f"\nEarly stopping: {args.patience} epoch 연속 개선 없음")
            break

    print("\n" + "=" * 64)
    print(f"MOVAR V7 종료: best epoch={best_epoch}, Val Mean Macro F1={best_f1:.6f}")
    print(f"V6(0.5918) 대비: {best_f1 - 0.5918:+.6f}")
    print(f"총 시간: {(time.perf_counter()-start)/3600:.2f}시간")
    print(f"결과: {output}")


if __name__ == "__main__":
    main()

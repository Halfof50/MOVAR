from pathlib import Path

import pandas as pd
import torch

from PIL import Image

from torch.utils.data import Dataset
from torchvision import transforms
from torchvision.transforms import InterpolationMode


BASE = Path(__file__).resolve().parent.parent

LABEL_COLS = [
    "value_1",
    "value_2",
    "value_3",
    "value_4",
    "value_5",
    "value_6",
]


# ==========================================
# 1. 이미지 전처리
# ==========================================

def get_transform():

    return transforms.Compose([

        # EUPE 입력 이미지 크기
        transforms.Resize(
            (224, 224),
            interpolation=InterpolationMode.BILINEAR,
            antialias=True
        ),

        # PIL Image → Tensor
        transforms.ToTensor(),

        # ImageNet 정규화
        transforms.Normalize(
            mean=[0.485, 0.456, 0.406],
            std=[0.229, 0.224, 0.225]
        )
    ])


# ==========================================
# 2. MOVAR Dataset
# ==========================================

class MOVARDataset(Dataset):

    def __init__(self, csv_path, transform=None):

        self.df = pd.read_csv(csv_path)

        self.transform = (
            transform
            if transform is not None
            else get_transform()
        )

        required_cols = ["image_path", *LABEL_COLS]

        missing = [
            col for col in required_cols
            if col not in self.df.columns
        ]

        if missing:
            raise ValueError(
                f"CSV에 필요한 컬럼이 없습니다: {missing}"
            )

        if self.df[required_cols].isnull().any().any():
            raise ValueError("이미지 경로 또는 라벨 결측치 발견")

        self.labels = self.df[LABEL_COLS].to_numpy(
            dtype="int64"
        )

        if not (
            (self.labels >= 0) &
            (self.labels <= 3)
        ).all():
            raise ValueError("라벨은 0~3 범위여야 합니다.")

        self.image_paths = self.df[
            "image_path"
        ].tolist()

    def __len__(self):

        return len(self.df)

    def __getitem__(self, idx):

        # 이미지 경로
        image_path = BASE / self.image_paths[idx]

        # 이미지 불러오기
        with Image.open(image_path) as img:
            image = img.convert("RGB")

        # 이미지 전처리
        image = self.transform(image)

        # 6개 증상 라벨
        labels = torch.tensor(
            self.labels[idx],
            dtype=torch.long
        )

        return image, labels
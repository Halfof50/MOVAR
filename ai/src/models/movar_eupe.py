from pathlib import Path

import torch
import torch.nn as nn


class MOVAREUPE(nn.Module):

    def __init__(
        self,
        repo_dir,
        weights_path,
        freeze_backbone=True
    ):
        super().__init__()

        repo_dir = Path(repo_dir).resolve()
        weights_path = Path(weights_path).resolve()

        if not (repo_dir / "hubconf.py").is_file():
            raise FileNotFoundError(
                f"EUPE 공식 코드가 없습니다: {repo_dir}"
            )

        if not weights_path.is_file():
            raise FileNotFoundError(
                f"사전학습 가중치가 없습니다: {weights_path}"
            )

        # 1. Meta EUPE-ViT-S/16 불러오기
        self.backbone = torch.hub.load(
            str(repo_dir),
            "eupe_vits16",
            source="local",
            pretrained=True,
            weights=str(weights_path)
        )

        # 2. EUPE 특징 벡터 크기
        self.feature_dim = self.backbone.embed_dim

        assert self.feature_dim == 384, (
            f"특징 차원 확인 필요: {self.feature_dim}"
        )

        # 3. 여섯 개의 분류 Head
        self.heads = nn.ModuleDict({

            "value_1": nn.Linear(384, 4),

            "value_2": nn.Linear(384, 4),

            "value_3": nn.Linear(384, 4),

            "value_4": nn.Linear(384, 4),

            "value_5": nn.Linear(384, 4),

            "value_6": nn.Linear(384, 4),

        })

        # 4. 초기 학습에서는 Backbone 고정 가능
        if freeze_backbone:
            for param in self.backbone.parameters():
                param.requires_grad = False

    def forward(self, images):

        # 이미지 특징 추출
        features = self.backbone.forward_features(
            images
        )

        # CLS Token: [Batch, 384]
        cls_token = features["x_norm_clstoken"]

        # 증상별 4개 클래스 예측
        outputs = {}

        for name, head in self.heads.items():
            outputs[name] = head(cls_token)

        return outputs
import torch

EUPE_REPO = "/home/yong/projects/EUPE"
WEIGHTS = "/home/yong/projects/movar-ai/weights/EUPE-ViT-S.pt"

device = torch.device("cuda" if torch.cuda.is_available() else "cpu")

model = torch.hub.load(
    EUPE_REPO,
    "eupe_vits16",
    source="local",
    weights=WEIGHTS
)

model = model.to(device)
model.eval()

x = torch.randn(1, 3, 224, 224).to(device)

with torch.no_grad():
    features = model.forward_features(x)

print("Device:", device)
print("CLS token shape:", features["x_norm_clstoken"].shape)
print("Patch token shape:", features["x_norm_patchtokens"].shape)

print("EUPE forward success!")
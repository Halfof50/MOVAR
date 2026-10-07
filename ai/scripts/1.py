from pathlib import Path
from collections import defaultdict
import hashlib

# =========================
# 경로 설정
# =========================
DATA_DIR = Path("data")

SPLITS = {
    "train": DATA_DIR / "train",
    "validation": DATA_DIR / "validation",
}

IMAGE_EXTS = {".jpg", ".jpeg", ".png"}
LABEL_EXTS = {".json"}


def get_files(root, extensions):
    return [
        p for p in root.rglob("*")
        if p.is_file() and p.suffix.lower() in extensions
    ]


def group_by_name(files):
    result = defaultdict(list)

    for file in files:
        result[file.name].append(file)

    return result


def file_hash(path, chunk_size=1024 * 1024):
    sha256 = hashlib.sha256()

    with open(path, "rb") as f:
        while True:
            chunk = f.read(chunk_size)

            if not chunk:
                break

            sha256.update(chunk)

    return sha256.hexdigest()


def check_duplicate_contents(grouped_files):
    same_content = 0
    different_content = 0
    conflicts = []

    duplicated = {
        name: paths
        for name, paths in grouped_files.items()
        if len(paths) > 1
    }

    for name, paths in duplicated.items():

        hashes = {
            file_hash(path)
            for path in paths
        }

        if len(hashes) == 1:
            same_content += 1
        else:
            different_content += 1
            conflicts.append((name, paths))

    return same_content, different_content, conflicts


def audit_split(split_name, split_dir):

    images_dir = split_dir / "images"
    labels_dir = split_dir / "labels"

    images = get_files(images_dir, IMAGE_EXTS)
    labels = get_files(labels_dir, LABEL_EXTS)

    image_groups = group_by_name(images)
    label_groups = group_by_name(labels)

    unique_images = len(image_groups)
    unique_labels = len(label_groups)

    duplicated_image_names = sum(
        1 for paths in image_groups.values()
        if len(paths) > 1
    )

    duplicated_label_names = sum(
        1 for paths in label_groups.values()
        if len(paths) > 1
    )

    print()
    print("=" * 70)
    print(f"{split_name.upper()}")
    print("=" * 70)

    print(f"전체 이미지 파일 수     : {len(images):,}")
    print(f"고유 이미지 파일명 수   : {unique_images:,}")
    print(f"중복 이미지 파일명 수   : {duplicated_image_names:,}")

    print()

    print(f"전체 라벨 파일 수       : {len(labels):,}")
    print(f"고유 라벨 파일명 수     : {unique_labels:,}")
    print(f"중복 라벨 파일명 수     : {duplicated_label_names:,}")

    print()
    print("중복 이미지 실제 내용 검사 중...")

    same, different, conflicts = check_duplicate_contents(image_groups)

    print(f"동일 파일 중복          : {same:,}")
    print(f"이름은 같지만 내용 다름 : {different:,}")

    if conflicts:
        print()
        print("⚠ 충돌 이미지 예시")

        for name, paths in conflicts[:10]:
            print()
            print(name)

            for path in paths:
                print("  ", path)

    return {
        "images": images,
        "labels": labels,
        "image_groups": image_groups,
        "label_groups": label_groups,
    }


results = {}

for split_name, split_dir in SPLITS.items():
    results[split_name] = audit_split(
        split_name,
        split_dir
    )


# =========================
# Train / Validation 중복
# =========================

train_names = set(
    results["train"]["image_groups"].keys()
)

val_names = set(
    results["validation"]["image_groups"].keys()
)

overlap = train_names & val_names

print()
print("=" * 70)
print("TRAIN / VALIDATION 중복 검사")
print("=" * 70)

print(f"Train 고유 이미지 : {len(train_names):,}")
print(f"Val 고유 이미지   : {len(val_names):,}")
print(f"Train-Val 중복     : {len(overlap):,}")

if overlap:

    print()
    print("⚠ Train / Validation에 동시에 존재하는 이미지 예시")

    for name in list(sorted(overlap))[:20]:
        print(name)


print()
print("=" * 70)
print("검사 완료")
print("=" * 70)
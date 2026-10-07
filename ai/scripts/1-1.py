from pathlib import Path
from collections import defaultdict
import hashlib


# ============================================================
# 경로 설정
# ============================================================

DATA_DIR = Path("data")

SPLITS = {
    "train": DATA_DIR / "train",
    "val": DATA_DIR / "val",
}

IMAGE_EXTS = {".jpg", ".jpeg", ".png"}
LABEL_EXTS = {".json"}


# ============================================================
# 파일 찾기
# ============================================================

def get_files(root, extensions):
    return [
        path
        for path in root.rglob("*")
        if path.is_file() and path.suffix.lower() in extensions
    ]


# ============================================================
# 같은 파일명끼리 그룹화
# ============================================================

def group_by_name(files):
    grouped = defaultdict(list)

    for file in files:
        grouped[file.name].append(file)

    return grouped


# ============================================================
# SHA-256 계산
# ============================================================

def file_hash(path, chunk_size=1024 * 1024):
    sha256 = hashlib.sha256()

    with open(path, "rb") as f:
        while True:
            chunk = f.read(chunk_size)

            if not chunk:
                break

            sha256.update(chunk)

    return sha256.hexdigest()


# ============================================================
# 중복 이미지 실제 내용 검사
# ============================================================

def check_duplicate_contents(grouped_files):
    duplicated = {
        name: paths
        for name, paths in grouped_files.items()
        if len(paths) > 1
    }

    total = len(duplicated)

    same_content = 0
    different_content = 0
    conflicts = []

    print(f"검사할 중복 파일명 수 : {total:,}")

    for index, (name, paths) in enumerate(duplicated.items(), start=1):

        hashes = set()

        for path in paths:
            hashes.add(file_hash(path))

        if len(hashes) == 1:
            same_content += 1
        else:
            different_content += 1
            conflicts.append((name, paths))

        # 진행률 출력
        if index % 5000 == 0 or index == total:
            percent = (index / total * 100) if total else 100

            print(
                f"진행률 : "
                f"{index:,} / {total:,} "
                f"({percent:.1f}%)"
            )

    return same_content, different_content, conflicts


# ============================================================
# Split 검사
# ============================================================

def audit_split(split_name, split_dir, run_hash=False):

    images_dir = split_dir / "images"
    labels_dir = split_dir / "labels"

    print()
    print("=" * 70)
    print(split_name.upper())
    print("=" * 70)

    # 경로 존재 확인
    if not images_dir.exists():
        print(f"❌ 이미지 폴더 없음 : {images_dir}")

    if not labels_dir.exists():
        print(f"❌ 라벨 폴더 없음 : {labels_dir}")

    images = get_files(images_dir, IMAGE_EXTS)
    labels = get_files(labels_dir, LABEL_EXTS)

    image_groups = group_by_name(images)
    label_groups = group_by_name(labels)

    unique_images = len(image_groups)
    unique_labels = len(label_groups)

    duplicated_image_names = sum(
        1
        for paths in image_groups.values()
        if len(paths) > 1
    )

    duplicated_label_names = sum(
        1
        for paths in label_groups.values()
        if len(paths) > 1
    )

    print(f"전체 이미지 파일 수     : {len(images):,}")
    print(f"고유 이미지 파일명 수   : {unique_images:,}")
    print(f"중복 이미지 파일명 수   : {duplicated_image_names:,}")

    print()

    print(f"전체 라벨 파일 수       : {len(labels):,}")
    print(f"고유 라벨 파일명 수     : {unique_labels:,}")
    print(f"중복 라벨 파일명 수     : {duplicated_label_names:,}")

    # --------------------------------------------------------
    # 이미지 / 라벨 고유 파일명 수 비교
    # --------------------------------------------------------

    print()
    print("[이미지 / 라벨 개수 비교]")

    if unique_images == unique_labels:
        print("✅ 고유 이미지 수와 고유 라벨 수가 같습니다.")
    else:
        print("⚠ 고유 이미지 수와 고유 라벨 수가 다릅니다.")

    # --------------------------------------------------------
    # SHA 검사
    # --------------------------------------------------------

    if run_hash:

        print()
        print("중복 이미지 실제 내용 검사 시작...")
        print("※ 시간이 오래 걸릴 수 있습니다.")
        print()

        same, different, conflicts = check_duplicate_contents(
            image_groups
        )

        print()
        print("[SHA-256 검사 결과]")
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

    else:
        print()
        print("Train SHA-256 검사는 이미 완료했으므로 생략합니다.")

    return {
        "images": images,
        "labels": labels,
        "image_groups": image_groups,
        "label_groups": label_groups,
    }


# ============================================================
# TRAIN 검사
# ============================================================

train_result = audit_split(
    "train",
    SPLITS["train"],
    run_hash=False,      # Train은 이미 SHA 검사 완료
)


# ============================================================
# VAL 검사
# ============================================================

val_result = audit_split(
    "val",
    SPLITS["val"],
    run_hash=True,       # Val만 SHA 검사
)


# ============================================================
# Train / Val 파일명 중복 검사
# ============================================================

train_names = set(
    train_result["image_groups"].keys()
)

val_names = set(
    val_result["image_groups"].keys()
)

overlap = train_names & val_names


print()
print("=" * 70)
print("TRAIN / VAL 중복 검사")
print("=" * 70)

print(f"Train 고유 이미지 : {len(train_names):,}")
print(f"Val 고유 이미지   : {len(val_names):,}")
print(f"Train-Val 중복     : {len(overlap):,}")


if overlap:

    print()
    print("⚠ Train과 Val에 동시에 존재하는 파일이 있습니다.")

    print()
    print("중복 파일 예시:")

    for name in sorted(overlap)[:20]:
        print(name)

else:

    print()
    print("✅ Train과 Val 사이에 동일한 파일명이 없습니다.")


# ============================================================
# 전체 고유 이미지 수
# ============================================================

total_unique = len(train_names | val_names)

print()
print("=" * 70)
print("전체 데이터 요약")
print("=" * 70)

print(f"Train 고유 이미지     : {len(train_names):,}")
print(f"Val 고유 이미지       : {len(val_names):,}")
print(f"Train-Val 중복        : {len(overlap):,}")
print(f"전체 고유 이미지      : {total_unique:,}")

print()
print("=" * 70)
print("검사 완료")
print("=" * 70)
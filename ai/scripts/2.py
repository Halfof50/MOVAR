from pathlib import Path
from collections import defaultdict
import hashlib


DATA_DIR = Path("data")

TRAIN_IMAGES = DATA_DIR / "train" / "images"
VAL_IMAGES = DATA_DIR / "val" / "images"

IMAGE_EXTS = {".jpg", ".jpeg", ".png"}


def get_images(root):
    return [
        p for p in root.rglob("*")
        if p.is_file() and p.suffix.lower() in IMAGE_EXTS
    ]


def group_by_name(files):
    result = defaultdict(list)

    for path in files:
        result[path.name].append(path)

    return result


def sha256(path, chunk_size=1024 * 1024):
    h = hashlib.sha256()

    with open(path, "rb") as f:
        while True:
            chunk = f.read(chunk_size)

            if not chunk:
                break

            h.update(chunk)

    return h.hexdigest()


def subject_key_1(filename):
    """
    파일명 예:
    0013_A2LEBJJDE00060O_1605839548962_2_TH.jpg

    첫 번째 토큰 기준
    """
    return filename.split("_")[0]


def subject_key_2(filename):
    """
    첫 번째 + 두 번째 토큰 기준 후보 ID
    """
    parts = filename.split("_")

    if len(parts) >= 2:
        return parts[0] + "_" + parts[1]

    return parts[0]


print("=" * 70)
print("파일 목록 읽는 중")
print("=" * 70)

train_files = get_images(TRAIN_IMAGES)
val_files = get_images(VAL_IMAGES)

train_groups = group_by_name(train_files)
val_groups = group_by_name(val_files)

train_names = set(train_groups.keys())
val_names = set(val_groups.keys())

overlap_names = sorted(train_names & val_names)

print(f"Train 고유 파일명 : {len(train_names):,}")
print(f"Val 고유 파일명   : {len(val_names):,}")
print(f"동일 파일명       : {len(overlap_names):,}")


# ============================================================
# 1. Train / Val 동일 파일명 → 실제 내용도 같은지 검사
# ============================================================

print()
print("=" * 70)
print("1. TRAIN / VAL 실제 이미지 중복 검사")
print("=" * 70)

exact_same = 0
different = 0

exact_examples = []
different_examples = []

total = len(overlap_names)

for i, name in enumerate(overlap_names, start=1):

    train_hashes = {
        sha256(path)
        for path in train_groups[name]
    }

    val_hashes = {
        sha256(path)
        for path in val_groups[name]
    }

    # Train과 Val에 동일한 바이트의 이미지가 하나라도 있는 경우
    if train_hashes & val_hashes:
        exact_same += 1

        if len(exact_examples) < 10:
            exact_examples.append(name)

    else:
        different += 1

        if len(different_examples) < 10:
            different_examples.append(name)

    if i % 500 == 0 or i == total:
        percent = i / total * 100 if total else 100

        print(
            f"진행률 : {i:,} / {total:,} "
            f"({percent:.1f}%)"
        )


print()
print("[결과]")
print(f"파일명 + 실제 내용까지 동일 : {exact_same:,}")
print(f"파일명은 같지만 내용 다름   : {different:,}")


if exact_examples:
    print()
    print("실제 중복 예시:")

    for name in exact_examples:
        print(" ", name)


if different_examples:
    print()
    print("파일명만 같고 내용은 다른 예시:")

    for name in different_examples:
        print(" ", name)


# ============================================================
# 2. 피험자 후보 ID 기준 Train / Val 중복 검사
# ============================================================

print()
print("=" * 70)
print("2. 피험자 후보 ID 누수 검사")
print("=" * 70)

train_subject_1 = {
    subject_key_1(name)
    for name in train_names
}

val_subject_1 = {
    subject_key_1(name)
    for name in val_names
}

overlap_subject_1 = train_subject_1 & val_subject_1


train_subject_2 = {
    subject_key_2(name)
    for name in train_names
}

val_subject_2 = {
    subject_key_2(name)
    for name in val_names
}

overlap_subject_2 = train_subject_2 & val_subject_2


print("[첫 번째 토큰 기준]")
print(f"Train ID 수      : {len(train_subject_1):,}")
print(f"Val ID 수        : {len(val_subject_1):,}")
print(f"Train-Val 중복 ID: {len(overlap_subject_1):,}")

print()

print("[첫 번째 + 두 번째 토큰 기준]")
print(f"Train ID 수      : {len(train_subject_2):,}")
print(f"Val ID 수        : {len(val_subject_2):,}")
print(f"Train-Val 중복 ID: {len(overlap_subject_2):,}")


if overlap_subject_2:

    print()
    print("중복 ID 예시:")

    for subject in sorted(overlap_subject_2)[:20]:
        print(" ", subject)


# ============================================================
# 3. 전체 요약
# ============================================================

print()
print("=" * 70)
print("최종 요약")
print("=" * 70)

print(f"Train 고유 이미지 파일명         : {len(train_names):,}")
print(f"Val 고유 이미지 파일명           : {len(val_names):,}")
print(f"Train-Val 동일 파일명            : {len(overlap_names):,}")
print(f"Train-Val 실제 동일 이미지       : {exact_same:,}")
print(f"동일 이름이지만 실제 내용 다름   : {different:,}")
print(f"후보 피험자 ID 중복(2토큰 기준)  : {len(overlap_subject_2):,}")

print()
print("검사 완료")
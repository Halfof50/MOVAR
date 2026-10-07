from pathlib import Path
import csv


# ============================================================
# 경로
# ============================================================

META_DIR = Path(r"C:\Users\USER\Documents\data\meta")

DATASET_INDEX = Path(
    r"C:\Users\USER\Downloads\movar_output\dataset_index.csv"
)

OUTPUT_DIR = Path(
    r"C:\Users\USER\Downloads\movar_output"
)


# ============================================================
# 1. dataset_index 읽기
# ============================================================

print("=" * 70)
print("1. dataset_index 읽기")
print("=" * 70)

dataset_names = set()

with open(
    DATASET_INDEX,
    "r",
    encoding="utf-8-sig",
    newline=""
) as f:

    reader = csv.DictReader(f)

    for row in reader:
        dataset_names.add(
            row["image_file_name"]
        )


print(
    f"dataset_index 고유 이미지 : "
    f"{len(dataset_names):,}"
)


# ============================================================
# 2. Meta JSON 읽기
# ============================================================

print()
print("=" * 70)
print("2. Meta JSON 읽기")
print("=" * 70)


if not META_DIR.exists():

    raise FileNotFoundError(
        f"Meta 폴더를 찾을 수 없습니다:\n{META_DIR}"
    )


meta_files = list(
    META_DIR.rglob("*.json")
)


print(
    f"Meta JSON 파일 : "
    f"{len(meta_files):,}"
)


meta_names = set()

invalid_meta_names = []


for path in meta_files:

    name = path.name

    # 예:
    # 0013_A2LEBJJDE00060O_1603508849507_5_RH_META.json
    #
    # ↓
    #
    # 0013_A2LEBJJDE00060O_1603508849507_5_RH.jpg

    if name.endswith("_META.json"):

        image_name = (
            name[:-10]
            + ".jpg"
        )

        meta_names.add(
            image_name
        )

    else:

        invalid_meta_names.append(
            name
        )


print(
    f"Meta에서 추출한 고유 이미지명 : "
    f"{len(meta_names):,}"
)

print(
    f"규칙과 다른 Meta 파일명       : "
    f"{len(invalid_meta_names):,}"
)


# ============================================================
# 3. 비교
# ============================================================

print()
print("=" * 70)
print("3. Meta ↔ Dataset 비교")
print("=" * 70)


matched = (
    meta_names
    & dataset_names
)

meta_only = (
    meta_names
    - dataset_names
)

dataset_only = (
    dataset_names
    - meta_names
)


print(
    f"Meta 고유 이미지        : "
    f"{len(meta_names):,}"
)

print(
    f"Dataset 고유 이미지     : "
    f"{len(dataset_names):,}"
)

print()

print(
    f"정상 매칭               : "
    f"{len(matched):,}"
)

print(
    f"Meta에만 존재           : "
    f"{len(meta_only):,}"
)

print(
    f"Dataset에만 존재        : "
    f"{len(dataset_only):,}"
)


# ============================================================
# 4. 결과 CSV 저장
# ============================================================

meta_only_path = (
    OUTPUT_DIR
    / "meta_only.csv"
)

dataset_only_path = (
    OUTPUT_DIR
    / "dataset_only.csv"
)


with open(
    meta_only_path,
    "w",
    newline="",
    encoding="utf-8-sig"
) as f:

    writer = csv.writer(f)

    writer.writerow(
        ["image_file_name"]
    )

    for name in sorted(meta_only):

        writer.writerow(
            [name]
        )


with open(
    dataset_only_path,
    "w",
    newline="",
    encoding="utf-8-sig"
) as f:

    writer = csv.writer(f)

    writer.writerow(
        ["image_file_name"]
    )

    for name in sorted(dataset_only):

        writer.writerow(
            [name]
        )


# ============================================================
# 5. 예시 출력
# ============================================================

if meta_only:

    print()
    print("Meta에만 존재하는 예시:")

    for name in sorted(meta_only)[:10]:
        print(" ", name)


if dataset_only:

    print()
    print("Dataset에만 존재하는 예시:")

    for name in sorted(dataset_only)[:10]:
        print(" ", name)


print()
print("=" * 70)
print("완료")
print("=" * 70)

print()
print("생성 파일:")
print(meta_only_path)
print(dataset_only_path)
from pathlib import Path
from collections import defaultdict
import json


DATA_DIR = Path("data")

SPLITS = {
    "train": DATA_DIR / "train",
    "val": DATA_DIR / "val",
}

REQUIRED_KEYS = [
    "image_id",
    "image_file_name",
    "value_1",
    "value_2",
    "value_3",
    "value_4",
    "value_5",
    "value_6",
]


def get_json_files(root):
    return [
        p for p in root.rglob("*.json")
        if p.is_file()
    ]


def label_vector(data):
    return (
        str(data["value_1"]),
        str(data["value_2"]),
        str(data["value_3"]),
        str(data["value_4"]),
        str(data["value_5"]),
        str(data["value_6"]),
    )


def audit_split(split_name, split_dir):

    label_dir = split_dir / "labels"

    files = get_json_files(label_dir)

    print()
    print("=" * 70)
    print(split_name.upper())
    print("=" * 70)

    print(f"JSON 파일 수 : {len(files):,}")

    records_by_image = defaultdict(list)

    invalid_json = []
    missing_keys = []
    invalid_values = []
    filename_mismatch = []

    for index, path in enumerate(files, start=1):

        try:
            with open(path, "r", encoding="utf-8-sig") as f:
                data = json.load(f)

        except Exception as e:
            invalid_json.append((path, str(e)))
            continue

        # 필수 키 검사
        missing = [
            key for key in REQUIRED_KEYS
            if key not in data
        ]

        if missing:
            missing_keys.append((path, missing))
            continue

        # value_1 ~ value_6 검사
        values = label_vector(data)

        if any(v not in {"0", "1", "2", "3"} for v in values):
            invalid_values.append(
                (path, values)
            )

        image_file_name = data["image_file_name"]

        # JSON 파일명과 image_file_name 비교
        expected_json_name = Path(image_file_name).with_suffix(".json").name

        if path.name != expected_json_name:
            filename_mismatch.append(
                (
                    path,
                    path.name,
                    expected_json_name,
                )
            )

        records_by_image[image_file_name].append(
            {
                "path": path,
                "image_id": data["image_id"],
                "values": values,
            }
        )

        if index % 20000 == 0:
            print(f"읽는 중 : {index:,} / {len(files):,}")

    # --------------------------------------------------------
    # 같은 이미지 파일명에 서로 다른 라벨이 있는지 검사
    # --------------------------------------------------------

    duplicated_names = 0
    same_labels = 0
    conflicting_labels = []

    for image_name, records in records_by_image.items():

        if len(records) <= 1:
            continue

        duplicated_names += 1

        vectors = {
            record["values"]
            for record in records
        }

        if len(vectors) == 1:
            same_labels += 1

        else:
            conflicting_labels.append(
                (image_name, records)
            )

    print()
    print("[기본 검사]")
    print(f"고유 image_file_name      : {len(records_by_image):,}")
    print(f"중복 image_file_name      : {duplicated_names:,}")

    print()
    print("[JSON 오류]")
    print(f"읽기 실패                : {len(invalid_json):,}")
    print(f"필수 키 누락             : {len(missing_keys):,}")
    print(f"잘못된 라벨 값           : {len(invalid_values):,}")
    print(f"파일명 불일치            : {len(filename_mismatch):,}")

    print()
    print("[중복 라벨 검사]")
    print(f"중복이지만 라벨 동일     : {same_labels:,}")
    print(f"같은 이미지명 라벨 충돌  : {len(conflicting_labels):,}")

    if conflicting_labels:

        print()
        print("⚠ 라벨 충돌 예시")

        for image_name, records in conflicting_labels[:10]:

            print()
            print(image_name)

            for record in records:
                print(
                    " ",
                    record["values"],
                    record["path"],
                )

    return records_by_image


train_records = audit_split(
    "train",
    SPLITS["train"],
)

val_records = audit_split(
    "val",
    SPLITS["val"],
)


# ============================================================
# Train / Val 동일 이미지명의 라벨 비교
# ============================================================

print()
print("=" * 70)
print("TRAIN / VAL 라벨 비교")
print("=" * 70)

train_names = set(train_records.keys())
val_names = set(val_records.keys())

overlap = train_names & val_names

same = 0
different = 0
conflicts = []

for image_name in overlap:

    train_vectors = {
        record["values"]
        for record in train_records[image_name]
    }

    val_vectors = {
        record["values"]
        for record in val_records[image_name]
    }

    if train_vectors == val_vectors:
        same += 1

    else:
        different += 1
        conflicts.append(
            (
                image_name,
                train_vectors,
                val_vectors,
            )
        )


print(f"Train-Val 동일 이미지명 : {len(overlap):,}")
print(f"Train-Val 라벨 동일     : {same:,}")
print(f"Train-Val 라벨 충돌     : {different:,}")


if conflicts:

    print()
    print("⚠ Train / Val 라벨 충돌 예시")

    for image_name, train_values, val_values in conflicts[:10]:

        print()
        print(image_name)
        print(" Train :", train_values)
        print(" Val   :", val_values)


print()
print("=" * 70)
print("검사 완료")
print("=" * 70)
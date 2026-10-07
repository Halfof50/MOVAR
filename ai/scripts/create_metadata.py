from pathlib import Path
from collections import defaultdict
import json
import csv
import tempfile


# ============================================================
# 1. Windows 데이터 경로
# ============================================================

DATA_DIR = Path(r"C:\Users\USER\Documents\data")

TRAIN_IMAGES = DATA_DIR / "train" / "images"
TRAIN_LABELS = DATA_DIR / "train" / "labels"

VAL_IMAGES = DATA_DIR / "val" / "images"
VAL_LABELS = DATA_DIR / "val" / "labels"


IMAGE_EXTENSIONS = {
    ".jpg",
    ".jpeg",
    ".png",
}

LABEL_KEYS = [
    "value_1",
    "value_2",
    "value_3",
    "value_4",
    "value_5",
    "value_6",
]


SPLITS = {
    "train": {
        "images": TRAIN_IMAGES,
        "labels": TRAIN_LABELS,
    },

    "val": {
        "images": VAL_IMAGES,
        "labels": VAL_LABELS,
    },
}


# ============================================================
# 2. 입력 폴더 검사
# ============================================================

print("=" * 70)
print("입력 경로 확인")
print("=" * 70)

print(f"DATA_DIR     : {DATA_DIR}")
print(f"TRAIN_IMAGES : {TRAIN_IMAGES}")
print(f"TRAIN_LABELS : {TRAIN_LABELS}")
print(f"VAL_IMAGES   : {VAL_IMAGES}")
print(f"VAL_LABELS   : {VAL_LABELS}")


required_dirs = [
    DATA_DIR,
    TRAIN_IMAGES,
    TRAIN_LABELS,
    VAL_IMAGES,
    VAL_LABELS,
]


for path in required_dirs:

    if not path.exists():

        raise FileNotFoundError(
            f"\n폴더를 찾을 수 없습니다:\n{path}"
        )


print()
print("✅ 입력 폴더 확인 완료")


# ============================================================
# 3. 실제 쓰기 가능한 출력 폴더 자동 선택
# ============================================================

def find_writable_output_dir():

    candidates = [
        Path.home() / "Downloads" / "movar_output",
        Path(tempfile.gettempdir()) / "movar_output",
    ]


    for candidate in candidates:

        try:

            candidate.mkdir(
                parents=True,
                exist_ok=True
            )

            test_file = (
                candidate
                / "__write_test__.txt"
            )


            with open(
                test_file,
                "w",
                encoding="utf-8"
            ) as f:

                f.write(
                    "write test success"
                )


            if not test_file.exists():

                continue


            test_file.unlink()

            return candidate


        except Exception as e:

            print()
            print(
                f"⚠ 저장 불가: {candidate}"
            )

            print(
                f"  이유: {e}"
            )


    raise RuntimeError(
        "\n"
        "CSV를 저장할 수 있는 폴더를 "
        "찾지 못했습니다."
    )


OUTPUT_DIR = find_writable_output_dir()


DATASET_INDEX_PATH = (
    OUTPUT_DIR
    / "dataset_index.csv"
)

IMAGE_COPIES_PATH = (
    OUTPUT_DIR
    / "image_copies.csv"
)

UNMATCHED_IMAGES_PATH = (
    OUTPUT_DIR
    / "unmatched_images.csv"
)

UNMATCHED_LABELS_PATH = (
    OUTPUT_DIR
    / "unmatched_labels.csv"
)


print()
print("=" * 70)
print("출력 경로 확인")
print("=" * 70)

print(
    f"OUTPUT_DIR : {OUTPUT_DIR}"
)

print()
print(
    "✅ CSV 저장 테스트 성공"
)

print(
    "이제 데이터 검사를 시작합니다."
)


# ============================================================
# 4. 이미지 파일명 파싱
# ============================================================

def parse_image_name(
    image_file_name
):

    """
    예:

    0013_A2LEBJJDE00060O_1603508849507_5_RH.jpg

    subject_id = 0013
    device_id  = A2LEBJJDE00060O
    capture_id = 1603508849507
    region_no  = 5
    location   = RH
    """

    stem = Path(
        image_file_name
    ).stem

    parts = stem.split("_")


    return {

        "subject_id":
            parts[0]
            if len(parts) >= 1
            else "",

        "device_id":
            parts[1]
            if len(parts) >= 2
            else "",

        "capture_id":
            parts[2]
            if len(parts) >= 3
            else "",

        "region_no":
            parts[3]
            if len(parts) >= 4
            else "",

        "location":
            parts[4]
            if len(parts) >= 5
            else "",
    }


# ============================================================
# 5. 라벨 JSON 읽기
# ============================================================

print()
print("=" * 70)
print("1. 라벨 JSON 읽기")
print("=" * 70)


label_records = {}

label_sources = defaultdict(
    list
)

json_errors = []

label_conflicts = []

total_json_count = 0


for split_name, dirs in SPLITS.items():

    label_dir = dirs[
        "labels"
    ]


    json_files = list(
        label_dir.rglob(
            "*.json"
        )
    )


    print()
    print(
        f"{split_name.upper()} "
        f"JSON 파일 : "
        f"{len(json_files):,}"
    )


    for index, json_path in enumerate(
        json_files,
        start=1
    ):

        try:

            with open(
                json_path,
                "r",
                encoding="utf-8-sig"
            ) as f:

                data = json.load(
                    f
                )


        except Exception as e:

            json_errors.append(
                {
                    "path":
                        str(
                            json_path
                        ),

                    "error":
                        str(e),
                }
            )

            continue


        # ----------------------------------------------------
        # 필수 키 검사
        # ----------------------------------------------------

        required_keys = [
            "image_id",
            "image_file_name",
            *LABEL_KEYS,
        ]


        missing_keys = [
            key
            for key
            in required_keys
            if key not in data
        ]


        if missing_keys:

            json_errors.append(
                {
                    "path":
                        str(
                            json_path
                        ),

                    "error":
                        (
                            "필수 키 누락: "
                            f"{missing_keys}"
                        ),
                }
            )

            continue


        image_name = str(
            data[
                "image_file_name"
            ]
        )


        # ----------------------------------------------------
        # value_1 ~ value_6 변환
        # ----------------------------------------------------

        try:

            values = {
                key:
                    int(
                        data[key]
                    )

                for key
                in LABEL_KEYS
            }


        except Exception as e:

            json_errors.append(
                {
                    "path":
                        str(
                            json_path
                        ),

                    "error":
                        (
                            "라벨 변환 실패: "
                            f"{e}"
                        ),
                }
            )

            continue


        # ----------------------------------------------------
        # 라벨 값 0~3 확인
        # ----------------------------------------------------

        if any(
            value
            not in {0, 1, 2, 3}

            for value
            in values.values()
        ):

            json_errors.append(
                {
                    "path":
                        str(
                            json_path
                        ),

                    "error":
                        (
                            "잘못된 라벨 값: "
                            f"{values}"
                        ),
                }
            )

            continue


        current_record = {

            "image_id":
                str(
                    data[
                        "image_id"
                    ]
                ),

            "image_file_name":
                image_name,

            **values,
        }


        # ----------------------------------------------------
        # 중복 JSON 라벨 일치 검사
        # ----------------------------------------------------

        if image_name in label_records:

            old_record = (
                label_records[
                    image_name
                ]
            )


            old_values = tuple(
                old_record[key]
                for key
                in LABEL_KEYS
            )

            new_values = tuple(
                current_record[key]
                for key
                in LABEL_KEYS
            )


            if (
                old_values
                != new_values
            ):

                label_conflicts.append(
                    {
                        "image_file_name":
                            image_name,

                        "old_values":
                            old_values,

                        "new_values":
                            new_values,

                        "json_path":
                            str(
                                json_path
                            ),
                    }
                )


        else:

            label_records[
                image_name
            ] = current_record


        label_sources[
            image_name
        ].append(
            {
                "split":
                    split_name,

                "label_path":
                    str(
                        json_path.resolve()
                    ),
            }
        )


        total_json_count += 1


        if (
            index % 20000 == 0
            or
            index == len(
                json_files
            )
        ):

            print(
                f"  진행 : "
                f"{index:,} / "
                f"{len(json_files):,}"
            )


print()
print("[라벨 결과]")

print(
    f"전체 JSON 파일       : "
    f"{total_json_count:,}"
)

print(
    f"고유 라벨 이미지     : "
    f"{len(label_records):,}"
)

print(
    f"JSON 오류            : "
    f"{len(json_errors):,}"
)

print(
    f"라벨 충돌            : "
    f"{len(label_conflicts):,}"
)


# ============================================================
# 6. 이미지 파일 읽기
# ============================================================

print()
print("=" * 70)
print("2. 이미지 파일 읽기")
print("=" * 70)


image_sources = defaultdict(
    list
)

total_image_count = 0


for split_name, dirs in SPLITS.items():

    image_dir = dirs[
        "images"
    ]


    image_files = [

        path

        for path
        in image_dir.rglob("*")

        if (
            path.is_file()

            and

            path.suffix.lower()
            in IMAGE_EXTENSIONS
        )
    ]


    print()
    print(
        f"{split_name.upper()} "
        f"이미지 파일 : "
        f"{len(image_files):,}"
    )


    for index, image_path in enumerate(
        image_files,
        start=1
    ):

        image_name = (
            image_path.name
        )


        image_sources[
            image_name
        ].append(
            {
                "split":
                    split_name,

                "image_path":
                    str(
                        image_path.resolve()
                    ),

                "source_folder":
                    image_path.parent.name,
            }
        )


        total_image_count += 1


        if (
            index % 20000 == 0
            or
            index == len(
                image_files
            )
        ):

            print(
                f"  진행 : "
                f"{index:,} / "
                f"{len(image_files):,}"
            )


print()
print("[이미지 결과]")

print(
    f"전체 물리 이미지 파일 : "
    f"{total_image_count:,}"
)

print(
    f"고유 이미지 파일명    : "
    f"{len(image_sources):,}"
)


# ============================================================
# 7. 이미지 / 라벨 매칭
# ============================================================

print()
print("=" * 70)
print("3. 이미지 / 라벨 매칭")
print("=" * 70)


image_names = set(
    image_sources.keys()
)

label_names = set(
    label_records.keys()
)


matched_names = (
    image_names
    &
    label_names
)

image_only = (
    image_names
    -
    label_names
)

label_only = (
    label_names
    -
    image_names
)


print(
    f"이미지 고유 이름 : "
    f"{len(image_names):,}"
)

print(
    f"라벨 고유 이름   : "
    f"{len(label_names):,}"
)

print(
    f"정상 매칭        : "
    f"{len(matched_names):,}"
)

print(
    f"이미지만 존재    : "
    f"{len(image_only):,}"
)

print(
    f"라벨만 존재      : "
    f"{len(label_only):,}"
)


# ============================================================
# 8. dataset_index 생성
# ============================================================

print()
print("=" * 70)
print("4. dataset_index 생성")
print("=" * 70)


dataset_rows = []


for image_name in sorted(
    matched_names
):

    label = label_records[
        image_name
    ]


    parsed = parse_image_name(
        image_name
    )


    copies = image_sources[
        image_name
    ]


    split_set = {

        copy["split"]

        for copy
        in copies
    }


    has_train = (
        "train"
        in split_set
    )

    has_val = (
        "val"
        in split_set
    )


    if (
        has_train
        and
        has_val
    ):

        original_split = (
            "both"
        )

    elif has_train:

        original_split = (
            "train"
        )

    else:

        original_split = (
            "val"
        )


    # --------------------------------------------------------
    # 실제 이미지 복사본 중 첫 번째 경로
    # --------------------------------------------------------

    image_paths = sorted(
        copy[
            "image_path"
        ]

        for copy
        in copies
    )


    representative_path = (
        image_paths[0]
    )


    row = {

        "image_id":
            label[
                "image_id"
            ],

        "image_file_name":
            image_name,


        "subject_id":
            parsed[
                "subject_id"
            ],

        "device_id":
            parsed[
                "device_id"
            ],

        "capture_id":
            parsed[
                "capture_id"
            ],

        "region_no":
            parsed[
                "region_no"
            ],

        "location":
            parsed[
                "location"
            ],


        "value_1":
            label[
                "value_1"
            ],

        "value_2":
            label[
                "value_2"
            ],

        "value_3":
            label[
                "value_3"
            ],

        "value_4":
            label[
                "value_4"
            ],

        "value_5":
            label[
                "value_5"
            ],

        "value_6":
            label[
                "value_6"
            ],


        "original_split":
            original_split,


        "has_train_copy":
            int(
                has_train
            ),

        "has_val_copy":
            int(
                has_val
            ),


        "image_copy_count":
            len(
                copies
            ),

        "label_copy_count":
            len(
                label_sources[
                    image_name
                ]
            ),


        "image_path":
            representative_path,
    }


    dataset_rows.append(
        row
    )


print(
    f"dataset_index 행 생성 완료 : "
    f"{len(dataset_rows):,}"
)


# ============================================================
# 9. dataset_index.csv 저장
# ============================================================

print()
print(
    "dataset_index.csv 저장 중..."
)


dataset_fields = [

    "image_id",
    "image_file_name",

    "subject_id",
    "device_id",
    "capture_id",
    "region_no",
    "location",

    "value_1",
    "value_2",
    "value_3",
    "value_4",
    "value_5",
    "value_6",

    "original_split",

    "has_train_copy",
    "has_val_copy",

    "image_copy_count",
    "label_copy_count",

    "image_path",
]


with open(
    DATASET_INDEX_PATH,
    "w",
    newline="",
    encoding="utf-8-sig"
) as f:

    writer = csv.DictWriter(
        f,
        fieldnames=dataset_fields
    )

    writer.writeheader()

    writer.writerows(
        dataset_rows
    )


print(
    f"✅ dataset_index.csv 저장 완료"
)


# ============================================================
# 10. image_copies.csv 저장
# ============================================================

print()
print(
    "image_copies.csv 저장 중..."
)


with open(
    IMAGE_COPIES_PATH,
    "w",
    newline="",
    encoding="utf-8-sig"
) as f:

    fields = [
        "image_file_name",
        "split",
        "source_folder",
        "image_path",
    ]


    writer = csv.DictWriter(
        f,
        fieldnames=fields
    )

    writer.writeheader()


    for image_name in sorted(
        image_sources.keys()
    ):

        for copy in image_sources[
            image_name
        ]:

            writer.writerow(
                {
                    "image_file_name":
                        image_name,

                    "split":
                        copy[
                            "split"
                        ],

                    "source_folder":
                        copy[
                            "source_folder"
                        ],

                    "image_path":
                        copy[
                            "image_path"
                        ],
                }
            )


print(
    "✅ image_copies.csv 저장 완료"
)


# ============================================================
# 11. 매칭 실패 목록
# ============================================================

if image_only:

    with open(
        UNMATCHED_IMAGES_PATH,
        "w",
        newline="",
        encoding="utf-8-sig"
    ) as f:

        writer = csv.writer(
            f
        )

        writer.writerow(
            [
                "image_file_name"
            ]
        )


        for name in sorted(
            image_only
        ):

            writer.writerow(
                [name]
            )


if label_only:

    with open(
        UNMATCHED_LABELS_PATH,
        "w",
        newline="",
        encoding="utf-8-sig"
    ) as f:

        writer = csv.writer(
            f
        )

        writer.writerow(
            [
                "image_file_name"
            ]
        )


        for name in sorted(
            label_only
        ):

            writer.writerow(
                [name]
            )


# ============================================================
# 12. 최종 통계
# ============================================================

train_only = sum(

    row[
        "original_split"
    ] == "train"

    for row
    in dataset_rows
)


val_only = sum(

    row[
        "original_split"
    ] == "val"

    for row
    in dataset_rows
)


both = sum(

    row[
        "original_split"
    ] == "both"

    for row
    in dataset_rows
)


subject_ids = {

    row[
        "subject_id"
    ]

    for row
    in dataset_rows

    if row[
        "subject_id"
    ]
}


print()
print("=" * 70)
print("최종 결과")
print("=" * 70)

print(
    f"dataset_index 행 수 : "
    f"{len(dataset_rows):,}"
)

print(
    f"고유 피험자 수       : "
    f"{len(subject_ids):,}"
)

print()

print(
    f"Train에만 존재      : "
    f"{train_only:,}"
)

print(
    f"Val에만 존재        : "
    f"{val_only:,}"
)

print(
    f"Train + Val 모두    : "
    f"{both:,}"
)

print()

print(
    f"이미지만 존재       : "
    f"{len(image_only):,}"
)

print(
    f"라벨만 존재         : "
    f"{len(label_only):,}"
)

print(
    f"JSON 오류           : "
    f"{len(json_errors):,}"
)

print(
    f"라벨 충돌           : "
    f"{len(label_conflicts):,}"
)

print()

print(
    "생성된 파일:"
)

print(
    DATASET_INDEX_PATH
)

print(
    IMAGE_COPIES_PATH
)


if image_only:

    print(
        UNMATCHED_IMAGES_PATH
    )


if label_only:

    print(
        UNMATCHED_LABELS_PATH
    )


print()
print("=" * 70)
print("완료")
print("=" * 70)
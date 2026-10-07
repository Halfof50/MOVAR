import csv
from pathlib import Path
from collections import Counter


# ============================================================
# 경로
# ============================================================

DATASET_INDEX = Path(
    r"C:\Users\USER\Downloads\movar_output\dataset_index.csv"
)

OUTPUT_PATH = Path(
    r"C:\Users\USER\Downloads\movar_output\class_distribution.csv"
)


# ============================================================
# 증상 이름
# ============================================================

LABEL_NAMES = {
    "value_1": "미세각질",
    "value_2": "피지과다",
    "value_3": "모낭사이홍반",
    "value_4": "모낭홍반농포",
    "value_5": "비듬",
    "value_6": "탈모",
}


# ============================================================
# 데이터 읽기
# ============================================================

counters = {
    key: Counter()
    for key in LABEL_NAMES
}

total = 0


with open(
    DATASET_INDEX,
    "r",
    encoding="utf-8-sig",
    newline=""
) as f:

    reader = csv.DictReader(f)

    for row in reader:

        total += 1

        for key in LABEL_NAMES:

            value = int(row[key])

            counters[key][value] += 1


# ============================================================
# 출력
# ============================================================

print("=" * 70)
print("전체 클래스 분포")
print("=" * 70)

print(f"전체 이미지 수 : {total:,}")


output_rows = []


for key, name in LABEL_NAMES.items():

    print()
    print("=" * 70)
    print(f"{key} - {name}")
    print("=" * 70)

    for cls in range(4):

        count = counters[key][cls]

        ratio = (
            count / total * 100
            if total > 0
            else 0
        )

        print(
            f"{cls}단계 : "
            f"{count:,}장 "
            f"({ratio:.2f}%)"
        )

        output_rows.append(
            {
                "label": key,
                "symptom": name,
                "class": cls,
                "count": count,
                "percentage": round(ratio, 2),
            }
        )


# ============================================================
# CSV 저장
# ============================================================

with open(
    OUTPUT_PATH,
    "w",
    encoding="utf-8-sig",
    newline=""
) as f:

    fieldnames = [
        "label",
        "symptom",
        "class",
        "count",
        "percentage",
    ]

    writer = csv.DictWriter(
        f,
        fieldnames=fieldnames
    )

    writer.writeheader()

    writer.writerows(output_rows)


print()
print("=" * 70)
print("완료")
print("=" * 70)

print()
print(f"저장 위치:")
print(OUTPUT_PATH)
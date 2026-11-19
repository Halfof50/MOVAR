import subprocess
import sys
from pathlib import Path


BASE = Path(__file__).resolve().parent

for script in [
    "01_prepare_333.py",
    "02_filter_shampoo.py",
    "03_match_mfds.py",
    "04_make_manual_catalog.py",
]:
    print()
    print("=" * 80)
    print("RUN:", script)
    print("=" * 80)

    result = subprocess.run(
        [
            sys.executable,
            str(BASE / script),
        ]
    )

    if result.returncode != 0:
        raise SystemExit(
            result.returncode
        )

print()
print("=" * 80)
print("완료")
print("data/output/04_shampoo_manual_all.csv")
print("RAW_INGREDIENTS 열에 전성분을 붙여넣으세요.")
print("그 다음: python 05_build_db_tables.py")
print("=" * 80)

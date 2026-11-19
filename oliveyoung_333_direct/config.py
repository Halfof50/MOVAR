from pathlib import Path

BASE = Path(__file__).resolve().parent
INPUT = BASE / "data" / "input"
OUTPUT = BASE / "data" / "output"

INPUT.mkdir(parents=True, exist_ok=True)
OUTPUT.mkdir(parents=True, exist_ok=True)

OLIVEYOUNG_CSV = INPUT / "oliveyoung_browser_products.csv"
MFDS_CSV = INPUT / "shampoo_products.csv"

PREPARED_CSV = OUTPUT / "01_oliveyoung_333_prepared.csv"
ALL_CLASSIFIED_CSV = OUTPUT / "02_all_products_classified.csv"
SHAMPOO_ONLY_CSV = OUTPUT / "02_shampoo_only.csv"
MFDS_MATCHED_CSV = OUTPUT / "03_shampoo_mfds_matched.csv"
MANUAL_CSV = OUTPUT / "04_shampoo_manual_all.csv"

DB_PRODUCTS_CSV = OUTPUT / "05_products_for_db.csv"
DB_INGREDIENTS_CSV = OUTPUT / "05_ingredients_for_db.csv"
DB_PRODUCT_INGREDIENTS_CSV = OUTPUT / "05_product_ingredients_for_db.csv"

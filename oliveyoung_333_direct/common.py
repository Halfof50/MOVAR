import re
import unicodedata


def clean_text(value):
    if value is None:
        return ""
    value = str(value).replace("\u00a0", " ")
    return re.sub(r"\s+", " ", value).strip()


def normalize_text(value):
    value = unicodedata.normalize("NFKC", clean_text(value).lower())
    return re.sub(r"[^0-9a-z가-힣]+", "", value)

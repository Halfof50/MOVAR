"""
전성분 텍스트 정규화

전성분은 제조사가 자유 형식으로 적은 문자열이다. 구분자와 표기가 제품마다 다르다.
여기서 하는 일은 두 가지.

 1. split_ingredients : 전성분 문자열을 성분 토큰 리스트로 자른다
 2. match_canonical   : 토큰을 대표 성분명으로 매칭한다

전체 문자열에 대한 부분 문자열 검색을 쓰지 않고 토큰 단위로 매칭한다.
전체 검색을 하면 '하이드록시에틸우레아' 안의 '우레아'가 '유레아'로 잡힌다.
토큰 단위로 끊은 뒤 제외 목록에 걸리는 토큰은 통째로 건너뛰는 방식으로 처리한다.
"""

import re

# 성분 표기 변형 → 대표 이름
ALIASES = {
    "덱스판테놀":     ["덱스판테놀"],
    "살리실릭애씨드": ["살리실릭애씨드", "소듐살리실레이트", "살리실산"],
    "멘톨":           ["엘-멘톨", "L-멘톨", "멘톨"],
    "나이아신아마이드": ["나이아신아마이드"],
    "비오틴":         ["비오틴", "바이오틴"],
    "징크피리치온":   ["징크피리치온"],
    "피록톤올아민":   ["피록톤올아민"],
    "클림바졸":       ["클림바졸"],
    "티트리":         ["티트리잎오일", "티트리잎추출물", "티트리오일", "티트리"],
    "카페인":         ["카페인"],
    "병풀":           ["마데카소사이드", "아시아티코사이드", "병풀추출물", "병풀잎추출물",
                       "병풀꽃/잎/줄기추출물", "센텔라아시아티카"],
    "다이포타슘글리시리제이트": ["다이포타슘글리시리제이트", "다이포타슘글리시리제이트액",
                                "글리시리제이트", "글리시리진"],
    "유레아":         ["유레아", "우레아"],
    "글라이콜릭애씨드": ["글라이콜릭애씨드"],
    "락틱애씨드":     ["락틱애씨드", "소듐락테이트"],
}

# 이름만 비슷하고 작용이 다른 성분. 이 문자열을 포함한 토큰은 매칭에서 제외한다.
EXCLUSIONS = {
    "하이드록시에틸우레아": "보습제. 유레아의 각질 작용과 무관",
    "하이드록시에틸유레아": "같은 성분 다른 표기",
    "유차나무":            "차나무(Camellia sinensis) 계열. 티트리(Melaleuca)와 다른 식물",
    "차나무":              "녹차나무. 티트리와 다른 식물",
    "카페인산":            "페놀산(caffeic acid). 카페인과 다른 물질",
}

# 성분 구분자.
# 슬래시는 쓰지 않는다. 데이터셋 146개 중 66개에 슬래시가 있는데
# '카프릴릭/카프릭트라이글리세라이드', '병풀꽃/잎/줄기추출물'처럼
# 대부분 성분명 내부 표기이고 구분자로 쓰인 건 1건뿐이다.
# 콤마가 전혀 없는 경우에만 슬래시를 구분자로 본다.
_SPLIT      = re.compile(r"[,，、;；|]|\s{2,}")
_SPLIT_ALT  = re.compile(r"[/|]|\s{2,}")

# 토큰에서 떼어낼 부가 표기
_PAREN   = re.compile(r"\([^)]*\)")
_PERCENT = re.compile(r"\d+(\.\d+)?\s*%")
_NOISE   = re.compile(r"(기타\s*성분|이상|이하|등$|^및\s*)")


def split_ingredients(text) -> list:
    """전성분 문자열 → 성분 토큰 리스트 (순서 유지, 중복 제거하지 않음)"""
    s = str(text or "")
    if not s or s.lower() == "nan":
        return []

    # 괄호 안은 함량·유래 표기가 많아 매칭을 방해한다.
    s = _PAREN.sub(" ", s)
    s = _PERCENT.sub(" ", s)
    s = s.replace("\n", " ").replace("\t", " ")

    if "," in s or "，" in s:
        pattern = _SPLIT
    else:
        # 슬래시를 구분자로 쓰는 경우. 성분명 내부의 슬래시는 미리 보호한다.
        for canon, names in ALIASES.items():
            for n in names:
                if "/" in n:
                    s = s.replace(n, n.replace("/", "／"))
        pattern = _SPLIT_ALT

    tokens = _apply(pattern, s)

    # 구분자 없이 한 칸 공백으로만 나열한 제품이 있다.
    # 토큰이 비정상적으로 적으면 공백 기준으로 다시 자른다.
    if len(tokens) < 5 and len(s) > 60:
        tokens = _apply(re.compile(r"\s+"), s)

    return tokens


def _apply(pattern, s: str) -> list:
    out = []
    for raw in pattern.split(s):
        t = _NOISE.sub(" ", raw)
        t = re.sub(r"\s+", "", t).strip(".·*-").replace("／", "/")
        if t:
            out.append(t)
    return out


def match_canonical(tokens) -> set:
    """성분 토큰 리스트 → 대표 성분명 집합"""
    found = set()
    for t in tokens:
        if any(ex in t for ex in EXCLUSIONS):
            continue
        for canon, names in ALIASES.items():
            if canon in found:
                continue
            if any(n in t for n in names):
                found.add(canon)
    return found


def find_ingredients(text) -> set:
    """전성분 문자열 → 대표 성분명 집합"""
    return match_canonical(split_ingredients(text))


if __name__ == "__main__":
    samples = [
        "정제수, 소듐라우레스설페이트, 하이드록시에틸우레아, 살리실릭애씨드, 엘-멘톨, 덱스판테놀",
        "정제수, 유차나무씨오일, 글리세린",
        "정제수, 티트리잎오일, 바이오틴, 나이아신아마이드, 징크피리치온, 덱스판테놀",
        "정제수/글리세린/병풀꽃/잎/줄기추출물/소듐락테이트",
    ]
    for s in samples:
        print(sorted(find_ingredients(s)), "<-", s[:50])

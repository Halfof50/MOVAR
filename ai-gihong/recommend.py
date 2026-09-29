import re
from pathlib import Path

import numpy as np
import pandas as pd
from sentence_transformers import SentenceTransformer

from ingredient_scores import SYMPTOMS, ingredient_scores

BASE = Path(__file__).parent
CSV = BASE / "data" / "products.csv"
EMBED_MODEL = "jhgan/ko-sroberta-multitask"

W_INGREDIENT, W_SIMILARITY, W_RATING = 0.5, 0.3, 0.2
M_REVIEWS = 2000         # IMDb 가중 평점 기준 리뷰 수 (하위 25% 리뷰 수 수준)
TOP_N = 5

SYMPTOM_KR = {
    "micro_keratin": "각질", "excess_sebum": "피지",
    "follicular_erythema": "두피 홍반", "follicular_pustule": "두피 염증",
    "dandruff": "비듬", "hair_loss": "탈모",
}

# 증상별 검색 문장 (고정)
SYMPTOM_QUERY = {
    "micro_keratin": "두피 각질과 노폐물을 정리해주는 스케일링 제품",
    "excess_sebum": "피지와 유분이 많은 지성 두피를 산뜻하게 관리하는 제품",
    "follicular_erythema": "붉어진 두피를 진정시키는 순한 제품",
    "follicular_pustule": "두피 트러블과 염증을 가라앉히는 저자극 제품",
    "dandruff": "비듬과 가려움을 줄여주는 제품",
    "hair_loss": "탈모 증상 완화와 모발 강화를 돕는 제품",
}

DAMAGE_CARE_WORDS = ["손상", "단백질", "리페어", "데미지", "케라틴", "펌", "염색"]

# 카테고리 보정: 제품 목적이 증상과 직접 맞는 경우
CATEGORY_BONUS = {
    ("scaler", "micro_keratin"): 0.6,
    ("scaler", "excess_sebum"): 0.3,
    ("tonic", "hair_loss"): 0.3,
}


# ---------- 데이터 준비 (서버 시작 시 1회) ----------

def clean_name(name: str) -> str:
    n = re.sub(r"\[[^\]]*\]|\([^)]*\)", " ", str(name))
    n = re.sub(r"\d+(\.\d+)?\s*(ml|ML|mL|g|G|L|매|개입)", " ", n)
    n = re.sub(r"(기획|단품|대용량|증정|더블|리필|세트|택\s*1|\d+종)", " ", n)
    return re.sub(r"\s+", " ", n).strip()


def build_text(row) -> str:
    parts = [clean_name(row["name"])]
    spec = str(row.get("spec", "")).strip()
    if spec and spec.lower() != "nan":
        parts.append(spec)
    return ". ".join(parts)


def load_products():
    df = pd.read_csv(CSV, encoding="utf-8-sig")
    df = df[df["category"].notna()].reset_index(drop=True)

    # 성분 점수
    scored = df["ingredients"].apply(ingredient_scores)
    for s in SYMPTOMS:
        df[f"sc_{s}"] = [v[0][s] for v in scored]
    df["evidence"] = [v[1] for v in scored]

    # 증상별 정규화 (증상마다 최고점이 다른 문제 보정)
    for s in SYMPTOMS:
        mx = df[f"sc_{s}"].max()
        df[f"nc_{s}"] = df[f"sc_{s}"] / mx if mx > 0 else 0.0

    # IMDb 가중 평점 (영화 평점사이트에 사용되는 공식, 리뷰가 적으면 전체 평균 쪽으로 끌어당기는 공식임)
    rating = pd.to_numeric(df["rating"], errors="coerce")
    reviews = pd.to_numeric(df["reviews"], errors="coerce").fillna(0)
    c = rating.mean()
    df["adj_rating"] = ((reviews / (reviews + M_REVIEWS)) * rating.fillna(c)
                        + (M_REVIEWS / (reviews + M_REVIEWS)) * c)
    lo, hi = df["adj_rating"].min(), df["adj_rating"].max()
    df["adj_rating_n"] = (df["adj_rating"] - lo) / (hi - lo) if hi > lo else 0.5

    df["text"] = df.apply(build_text, axis=1)
    df["price_num"] = pd.to_numeric(df["price"], errors="coerce").fillna(0)
    return df


def load_embeddings(df):
    model = SentenceTransformer(EMBED_MODEL)
    prod_vec = model.encode(df["text"].tolist(), normalize_embeddings=True)
    sym_vec = {s: model.encode(q, normalize_embeddings=True)
               for s, q in SYMPTOM_QUERY.items()}
    return prod_vec, sym_vec


# ---------- 추천 (요청마다) ----------

def similarity(active, vectors):
    """활성 증상별 유사도를 심각도 제곱으로 가중 평균"""
    prod_vec, sym_vec = vectors
    total_w = sum(lv ** 2 for lv in active.values())
    sim = np.zeros(len(prod_vec))
    for sym, lv in active.items():
        sim += (lv ** 2) * (prod_vec @ sym_vec[sym])
    return sim / total_w


def make_reason(row, active, matched):
    top = sorted(active, key=lambda s: -active[s])[:2]
    hit = [SYMPTOM_KR[s] for s in top if row[f"sc_{s}"] > 0]
    txt = f"{', '.join(hit)} 관리에 맞는 제품" if hit else "두피 관리용 제품"
    if matched:
        txt += f" ({', '.join(matched[:3])} 함유)"
    return txt


def _to_item(r, active, reason=None):
    matched = sorted({i for s in active for i in r["evidence"][s]}) if active else []
    return {
        "name": clean_name(r["name"]),
        "price": int(r["price_num"]),
        "rating": None if pd.isna(r["rating"]) else float(r["rating"]),
        "reviews": int(pd.to_numeric(r["reviews"], errors="coerce") or 0),
        "category": r["category"],
        "image": r["image"],
        "link": r["link"],
        "reason": reason or make_reason(r, active, matched),
        "_score": round(float(r["score"]), 3),
        "_ing": round(float(r["s_ing"]), 3),
        "_sim": round(float(r["s_sim"]), 3),
        "_rating_adj": round(float(r["adj_rating"]), 2),
    }


def normalize_symptoms(symptoms: dict) -> dict:
    """{"excess_sebum": 2} 와 {"excess_sebum": {"level": 2}} 둘 다 허용"""
    out = {}
    for k, v in (symptoms or {}).items():
        if k not in SYMPTOMS:
            continue
        lv = v.get("level", 0) if isinstance(v, dict) else v
        try:
            out[k] = max(0, min(3, int(lv)))
        except (TypeError, ValueError):
            out[k] = 0
    return out


def recommend(scalp_type, symptoms, filters, df, vectors, top_n=TOP_N):
    
    # scalp_type : "지성" 등 (현재 점수 계산에는 쓰지 않고 추천 이유 표기용, LLM 리포트가 추후 지정정)
    # symptoms   : 증상별 심각도 0~3
    # filters    : None 이면 전체 후보. {"category":..., "price_max":..., "price_min":...}
   
    filters = filters or {}
    symptoms = normalize_symptoms(symptoms)
    active = {k: v for k, v in symptoms.items() if v >= 1}

    cand = df.copy()
    if filters.get("category"):
        cand = cand[cand["category"] == filters["category"]]
    if filters.get("price_max"):
        cand = cand[cand["price_num"] <= filters["price_max"]]
    if filters.get("price_min"):
        cand = cand[cand["price_num"] >= filters["price_min"]]
    if cand.empty:
        return []

    # 증상이 하나도 없는 경우: 기능성 성분이 적은 데일리 샴푸 우선
    if not active:
        daily = cand[cand["category"] == "shampoo"]
        mild_only = daily[~daily["name"].str.contains(
            "|".join(DAMAGE_CARE_WORDS), na=False)]
        if not mild_only.empty:
            cand = mild_only
        elif not daily.empty:
            cand = daily
        mild = 1 - cand[[f"nc_{s}" for s in SYMPTOMS]].max(axis=1)
        cand = cand.assign(
            s_ing=mild, s_sim=0.0,
            score=(W_INGREDIENT + W_SIMILARITY) * mild + W_RATING * cand["adj_rating_n"],
        )
        top = cand.sort_values("score", ascending=False).head(top_n)
        return [_to_item(r, {}, "현재 두피 상태가 양호해 자극이 적은 데일리 제품")
                for _, r in top.iterrows()]

    # 1. 성분 점수 (활성 증상을 심각도 제곱으로 가중 평균)
    w = {s: lv ** 2 for s, lv in active.items()}
    total = sum(w.values())
    ing = sum(cand[f"nc_{s}"] * wt for s, wt in w.items()) / total


    bonus = pd.Series(0.0, index=cand.index)
    for (cat, sym), val in CATEGORY_BONUS.items():
        if sym in active:
            bonus += (cand["category"] == cat) * val * (active[sym] ** 2) / total
    ing = (ing + bonus) / (1 + bonus.max() if bonus.max() > 0 else 1)

    # 2. 임베딩 유사도
    sim_all = similarity(active, vectors)
    sim = pd.Series(sim_all[cand.index.values], index=cand.index)
    sim = (sim - sim.min()) / (sim.max() - sim.min() + 1e-9)

    cand = cand.assign(
        s_ing=ing, s_sim=sim,
        score=W_INGREDIENT * ing + W_SIMILARITY * sim + W_RATING * cand["adj_rating_n"],
    )

    top = cand.sort_values("score", ascending=False).head(top_n)
    return [_to_item(r, active) for _, r in top.iterrows()]


# ---------- 터미널 테스트 ----------

if __name__ == "__main__":
    SYMPTOM_LIST = [
        ("micro_keratin", "미세각질"), ("excess_sebum", "피지과다"),
        ("follicular_erythema", "모낭사이홍반"), ("follicular_pustule", "모낭홍반농포"),
        ("dandruff", "비듬"), ("hair_loss", "탈모"),
    ]

    df = load_products()
    vectors = load_embeddings(df)
    print(f"상품 {len(df)}개 준비 완료\n")

    while True:
        print("증상별 심각도 (0~3, 엔터=0 / q 종료)")
        levels = {}
        quit_now = False
        for key, kr in SYMPTOM_LIST:
            v = input(f"  {kr:8s}: ").strip() or "0"
            if v.lower() == "q":
                quit_now = True
                break
            levels[key] = int(v) if v in "0123" else 0
        if quit_now:
            break

        cat = input("카테고리(엔터=전체): ").strip() or None
        pmax = input("최대 가격(엔터=제한없음): ").strip()
        filters = {"category": cat, "price_max": int(pmax) if pmax else None}

        for i, p in enumerate(recommend("", levels, filters, df, vectors), 1):
            print(f"\n{i}. [{p['category']}] {p['name'][:45]}")
            print(f"   {p['price']:,}원 / 별점 {p['rating']} ({p['reviews']}건 → 보정 {p['_rating_adj']})")
            print(f"   점수 {p['_score']} (성분 {p['_ing']} / 유사도 {p['_sim']})")
            print(f"   {p['reason']}")
        print("\n" + "=" * 55 + "\n")
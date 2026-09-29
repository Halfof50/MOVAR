import pandas as pd
from sentence_transformers import SentenceTransformer

SYMPTOM_KR = {
    "micro_keratin": "각질", "excess_sebum": "피지",
    "follicular_erythema": "두피 홍반", "follicular_pustule": "두피 염증",
    "dandruff": "비듬", "hair_loss": "탈모",
}

SYMPTOM_LIST = [
    ("micro_keratin", "미세각질"),
    ("excess_sebum", "피지과다"),
    ("follicular_erythema", "모낭사이홍반"),
    ("follicular_pustule", "모낭홍반농포"),
    ("dandruff", "비듬"),
    ("hair_loss", "탈모"),
]

KEY_INGREDIENTS = [
    "살리실릭애씨드", "피록톤올아민", "징크피리치온", "클림바졸",
    "멘톨", "박하추출물", "티트리", "병풀추출물", "마데카소사이드",
    "바이오틴", "비오틴", "카페인", "한련초추출물", "하수오뿌리추출물",
    "맥문동뿌리추출물", "측백나무잎추출물", "덱스판테놀",
]

print("모델 로딩 중...")
model = SentenceTransformer("jhgan/ko-sroberta-multitask")
df = pd.read_csv("data/products_tagged.csv", encoding="utf-8-sig")


def make_text(row):
    found = [g for g in KEY_INGREDIENTS if g in str(row["ingredients"])]
    parts = [str(row["name"])]
    if found:
        parts.append(", ".join(found[:8]) + " 함유")
    kr = [SYMPTOM_KR[t] for t in str(row["symptom_tags"]).split(",") if t in SYMPTOM_KR]
    if kr:
        parts.append(", ".join(kr) + " 관리용")
    return ". ".join(parts)


def build_query(active):
    items = sorted(active.items(), key=lambda x: -x[1])
    parts = [f"{SYMPTOM_KR[s]} {'심함' if lv == 3 else '있음' if lv == 2 else '약간'}"
             for s, lv in items]
    return ", ".join(parts) + " 상태의 두피에 맞는 샴푸"


def input_symptoms():
    print("증상별 심각도 입력 (0=양호 1=경증 2=중등도 3=중증, 엔터=0)\n")
    result = {}
    for key, kr in SYMPTOM_LIST:
        while True:
            v = input(f"  {kr:8s}: ").strip() or "0"
            if v in "0123" and len(v) == 1:
                result[key] = int(v)
                break
            print("    0~3 중에 입력하세요")
    return result


texts = [make_text(r) for _, r in df.iterrows()]
vectors = model.encode(texts, normalize_embeddings=True)
print(f"상품 {len(df)}개 준비 완료\n")

while True:
    levels = input_symptoms()
    active = {k: v for k, v in levels.items() if v >= 1}
    if not active:
        print("증상 없음. 종료합니다.")
        break

    query = build_query(active)
    print(f"\n검색 문장: {query}")

    q_vec = model.encode(query, normalize_embeddings=True)
    df["sim"] = vectors @ q_vec

    cand = df[df["symptom_tags"].str.contains("|".join(active.keys()), na=False)].copy()
    if len(cand) == 0:
        print("해당 증상 상품 없음 → 전체에서 유사도순\n")
        cand = df.copy()
    else:
        print(f"후보 {len(cand)}개\n")

    def score(row):
        tags = str(row["symptom_tags"]).split(",")
        s = sum(lv * lv for sym, lv in active.items() if sym in tags)
        s += max(0, 4 - len(tags))
        s += float(row["rating"]) / 5 * 0.5 if pd.notna(row["rating"]) else 0
        s += row["sim"] * 5
        return s

    cand["score"] = cand.apply(score, axis=1)
    top = cand.sort_values("score", ascending=False).head(5)

    for i, (_, r) in enumerate(top.iterrows(), 1):
        print(f"{i}. {str(r['name'])[:40]}")
        print(f"   {r['price']}원 / 별점 {r['rating']} / 유사도 {r['sim']:.3f} / 점수 {r['score']:.2f}")
        print(f"   태그: {r['symptom_tags']}\n")

    print("=" * 55 + "\n")
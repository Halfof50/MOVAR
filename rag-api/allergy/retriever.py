# -*- coding: utf-8 -*-
"""MOVAR 알레르기 지식 검색. 검증한 2차 테스트의 검색 코드를 분리함.

명칭/동의어 엄격 일치. 코사인 유사도는 검증되지 않은 알레르기 동등성에 사용하지 않음.
"""
from __future__ import annotations
from collections import defaultdict
import csv
import hashlib
import json
from pathlib import Path
import re
import unicodedata
import numpy as np

DB_FIELDS = ("알레르기명", "동의어", "구분", "관련성분명", "관계")
BAD_ORIGIN = "원료 출처 불명"
UNKNOWN_MARKER = "DB에 관련성분 미등록"
EMBED_MODEL = "jhgan/ko-sroberta-multitask"

def norm(value: str) -> str:
    """철자 자체는 바꾸지 않고 공백/대소문자/유니코드만 표준화."""
    x = unicodedata.normalize("NFKC", str(value or "")).lower().strip()
    return re.sub(r"\s+", "", x)


def read_csv(path: Path) -> list[dict]:
    with path.open("r", encoding="utf-8-sig", newline="") as f:
        return list(csv.DictReader(f))


def aliases(text: str) -> list[str]:
    return [x.strip() for x in re.split(r"\s*\|\s*", text or "") if x.strip()]


def ingredient_tokens(text: str) -> set[str]:
    """성분명 단위로 비교. 부분문자열 검출로 식품명/원료를 오인하지 않음.

    원본에 옵션 안내가 섞인 상품은 검수 대상으로 남기며, 임의 분리하지 않음.
    """
    # 함량 표기 (2,000ppm)의 쉼표가 성분 구분자로 잘못 처리되지 않도록 선제 제거.
    text = re.sub(r"\(\s*[\d,.]+\s*(?:ppm|%)\s*\)", "", text or "", flags=re.I)
    # 슬래시(/)는 화학 성분명 내부에도 등장하므로 구분자로 사용하지 않음.
    parts = re.split(r"[,，、;；@\n\r]+", text)
    cleaned = []
    for part in parts:
        part = re.sub(r"^\s*(?:\[[^\]]{1,100}\]|\*?리뉴얼\s*후\s*)+", "", part).strip()
        part = re.sub(r"\s*\(\s*[\d,.]+\s*(?:ppm|%)\s*\)\s*$", "", part, flags=re.I)
        if part:
            cleaned.append(norm(part))
    return set(cleaned)


def ingredient_is_listed(name: str, original_text: str, tokens: set[str]) -> bool:
    if norm(name) in tokens:
        return True
    # 일부 제품은 원본 전성분이 쉼표 없이 공백으로 나열되어 있음.
    # 이때만 한국어 단어 경계를 이용해 보조 검출하며, 유제놀 != 아이소유제놀처럼
    # 성분명의 부분문자열 중복을 절대 동일한 성분으로 취급하지 않음.
    if len(tokens) > 4:
        return False
    text = unicodedata.normalize("NFKC", original_text or "").lower()
    target = unicodedata.normalize("NFKC", name).lower().strip()
    pat = r"(?<![가-힣a-z0-9])" + re.escape(target) + r"(?![가-힣a-z0-9])"
    return re.search(pat, text) is not None


class AllergyKB:
    def __init__(self, db_file: Path, work_dir: Path, use_embedding: bool, model_name: str, cosine_threshold: float = 0.8):
        self.path = db_file
        self.rows = read_csv(db_file)
        if not self.rows or not set(DB_FIELDS).issubset(self.rows[0]):
            raise ValueError(f"알레르기 DB 5개 컬럼 확인: {DB_FIELDS}")
        self.work_dir = work_dir
        self.use_embedding = use_embedding
        self.model_name = model_name
        # 임계값은 아직 캘리브레이션하지 않은 진단용 초기 설정으로, 자동 수용에 사용하지 않음.
        self.cosine_threshold = cosine_threshold
        self.alias_to_name = defaultdict(set)
        self.ingredient_rows = defaultdict(list)
        self.group_children = {}
        self.allergen_names = set()
        for row in self.rows:
            name = row["알레르기명"].strip()
            if not name:
                continue
            self.allergen_names.add(name)
            for term in [name] + aliases(row["동의어"]):
                self.alias_to_name[norm(term)].add(name)
            ingredient = row["관련성분명"].strip()
            if ingredient:
                self.ingredient_rows[name].append(row)
            if row["관계"].startswith("포함 식품:"):
                self.group_children[name] = [x.strip() for x in row["관계"].split(":", 1)[1].split("·") if x.strip()]

        # 미등록 항목도 '명칭 존재'와 '성분 지식 있음'을 구분해서 보존.
        self.semantic_name_list = sorted(self.allergen_names)
        self.valid_rows = [r for r in self.rows if r["관련성분명"].strip()]
        self.doc_texts = [
            f"알레르기: {r['알레르기명']}. 화장품 원료: {r['관련성분명']}. 관계: {r['관계']}"
            for r in self.valid_rows
        ]
        self.model = None
        self.name_vectors = None
        self.doc_vectors = None
        self._query_cache = {}
        if use_embedding:
            self.load_index()

    def load_index(self):
        try:
            from sentence_transformers import SentenceTransformer
        except ImportError as exc:
            raise RuntimeError("임베딩 패키지 누락: pip install sentence-transformers") from exc
        self.work_dir.mkdir(parents=True, exist_ok=True)
        hashstr = hashlib.sha256(self.path.read_bytes()).hexdigest()
        params = {"db_sha256": hashstr, "model": self.model_name, "count": len(self.valid_rows),
                  "allergen_count": len(self.semantic_name_list)}
        meta_file = self.work_dir / "index_meta.json"
        name_file = self.work_dir / "allergen_name_vectors.npy"
        doc_file = self.work_dir / "knowledge_vectors.npy"
        print("[임베딩] 모델 로드:", self.model_name, flush=True)
        self.model = SentenceTransformer(self.model_name)
        cached = False
        if all(p.exists() for p in (meta_file, name_file, doc_file)):
            try:
                if json.loads(meta_file.read_text(encoding="utf-8")) == params:
                    names, docs = np.load(name_file), np.load(doc_file)
                    if names.shape[0] == len(self.semantic_name_list) and docs.shape[0] == len(self.valid_rows):
                        self.name_vectors, self.doc_vectors = names, docs
                        cached = True
            except (OSError, ValueError, json.JSONDecodeError):
                pass
        if not cached:
            print(f"[임베딩] DB 변경 감지: 알레르기명 {len(self.semantic_name_list)}개, 원료관계 {len(self.valid_rows)}개 벡터 생성", flush=True)
            self.name_vectors = self.model.encode(
                self.semantic_name_list, batch_size=32, show_progress_bar=True, convert_to_numpy=True,
                normalize_embeddings=True).astype(np.float32)
            self.doc_vectors = self.model.encode(
                self.doc_texts, batch_size=32, show_progress_bar=True, convert_to_numpy=True,
                normalize_embeddings=True).astype(np.float32)
            np.save(name_file, self.name_vectors)
            np.save(doc_file, self.doc_vectors)
            meta_file.write_text(json.dumps(params, indent=2, ensure_ascii=False), encoding="utf-8")
        else:
            print("[임베딩] 기존 인덱스 재사용", flush=True)

    def qvec(self, query: str):
        if query not in self._query_cache:
            v = self.model.encode([query], convert_to_numpy=True, normalize_embeddings=True)[0].astype(np.float32)
            self._query_cache[query] = v
        return self._query_cache[query]

    def _suggest(self, text: str, k: int = 3) -> list[dict]:
        """OOD 진단용: 코사인 상위 후보는 검증된 동일 알레르겐이 아님."""
        if not self.use_embedding:
            return []
        scores = self.name_vectors @ self.qvec(text)
        indices = np.argsort(-scores)[:k]
        return [{"name": self.semantic_name_list[i], "cosine": round(float(scores[i]), 4),
                 "diagnostic_threshold_pass": bool(scores[i] >= self.cosine_threshold),
                 "verified_alias": False} for i in indices]

    def resolve(self, allergy: str):
        """매핑은 엄격한 한국어 표준명/동의어만; 복합 입력은 두 원래 항목으로 분리."""
        components = [allergy]
        # 정확한 전체 별칭을 최우선 검사. '새우/갑각류'와 같은 이전 테스트 입력만 분리.
        if norm(allergy) not in self.alias_to_name and "/" in allergy:
            components = [p.strip() for p in allergy.split("/") if p.strip()]
        names = set()
        unknown = []
        ambiguous = []
        for term in components:
            targets = self.alias_to_name.get(norm(term), set())
            if len(targets) == 1:
                names.update(targets)
            elif len(targets) == 0:
                unknown.append(term)
            else:
                ambiguous.append(term)
        # 상위 식품군은 동의어로 취급하지 않고 구성 식품을 별도로 찾아 확장.
        included = set(names)
        for name in names:
            for child in self.group_children.get(name, []):
                child_targets = self.alias_to_name.get(norm(child), set())
                if len(child_targets) == 1:
                    included.update(child_targets)
        suggestions = {term: self._suggest(term) for term in unknown + ambiguous}
        return {"matched": sorted(names), "expanded": sorted(included),
                "unknown": unknown, "ambiguous": ambiguous, "suggestions_unverified": suggestions,
                "status": "exact" if not unknown and not ambiguous else "unverified"}

    def retrieve(self, allergy: str, products: list[dict], max_examples: int = 20, max_hits: int = 24):
        resolved = self.resolve(allergy)
        names = resolved["expanded"]
        related = [r for name in names for r in self.ingredient_rows.get(name, [])]
        # 상품 성분은 전체 텍스트 부분검색이 아니라 성분명 단위로 비교.
        by_product = []
        hit_row_indices = set()
        for item in products:
            tokens = ingredient_tokens(item["ingredients"])
            hits, uncertain = [], []
            for ridx, row in enumerate(related):
                if not ingredient_is_listed(row["관련성분명"], item["ingredients"], tokens):
                    continue
                entry = {"알레르기": row["알레르기명"], "성분": row["관련성분명"], "관계": row["관계"]}
                if BAD_ORIGIN in row["관계"]:
                    uncertain.append(entry)
                else:
                    hits.append(entry)
                hit_row_indices.add(ridx)
            by_product.append({"product_id": item["product_id"], "명시된_관련원료": hits[:max_hits],
                               "출처불명_원료": uncertain[:max_hits]})
        # 사용자 알레르기가 검증된 이름으로 매칭된 경우에 한해 유사도는 내부 DB 설명행의 정렬에만 사용.
        scored = []
        vector_sims = None
        if self.use_embedding and related:
            # 메타데이터에서 행 위치를 매번 찾지 않도록 동등한 5개 값으로 찾아 복수 항목도 안전히 처리.
            id_map = {id(row): i for i, row in enumerate(self.valid_rows)}
            query = f"알레르기 {allergy} 관련 화장품 원료"
            vector_sims = self.doc_vectors @ self.qvec(query)
        for ridx, row in enumerate(related):
            if BAD_ORIGIN in row["관계"]:
                continue
            sim = float(vector_sims[id_map[id(row)]]) if vector_sims is not None else 0.0
            scored.append((0 if ridx in hit_row_indices else 1, -sim, row["알레르기명"], row["관련성분명"], row))
        scored.sort(key=lambda x: x[:4])
        examples = [{"알레르기": r["알레르기명"], "성분": r["관련성분명"], "관계": r["관계"]}
                    for _, _, _, _, r in scored[:max_examples]]
        # 참조로만 쓰는 식품군 구성: 실제 동일 성분 관계가 아님.
        groups = {name: self.group_children[name] for name in resolved["matched"] if name in self.group_children}
        context = {"확인된_알레르기명": resolved["matched"], "관련_식품군_구성": groups,
                   "검색된_성분_예시": examples, "상품별_표기확인": by_product,
                   "주의": "'식품 유래 표기'는 임상 알레르기 위험 확정이 아니다. '출처불명'은 직접 매칭 금지. 부분문자열·코사인 유사도만으로 판정 금지."}
        # 미검증 OOD 후보는 context에 넣지 않음.
        return {"resolution": resolved, "context": context,
                "knowledge_row_count": len(related),
                "confirmed_hit_count": sum(len(x["명시된_관련원료"]) for x in by_product),
                "uncertain_hit_count": sum(len(x["출처불명_원료"]) for x in by_product)}

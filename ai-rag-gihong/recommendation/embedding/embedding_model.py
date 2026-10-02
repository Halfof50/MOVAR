"""
임베딩 모델 래퍼

운용 방침
- 사전학습 한국어 문장 임베딩 모델을 그대로 쓴다. 파인튜닝하지 않는다.
- 벡터는 L2 정규화해서 반환한다. 정규화하면 내적이 코사인 유사도와 같아지므로
  검색 단계에서 내적 한 번으로 끝난다.

백엔드가 두 개 있다.
- SentenceTransformerEmbedder : 실제 사용. jhgan/ko-sroberta-multitask
- HashingEmbedder             : 모델을 못 받는 환경에서 파이프라인 동작만 확인하는 용도.
                                검색 품질을 평가하는 데 쓰면 안 된다.
"""

import numpy as np

from recommendation.config import EMBED_DIM, EMBED_MODEL


def l2_normalize(v: np.ndarray) -> np.ndarray:
    v = np.asarray(v, dtype="float32")
    if v.ndim == 1:
        v = v[None, :]
    norm = np.linalg.norm(v, axis=1, keepdims=True)
    norm[norm == 0] = 1.0
    return v / norm


class SentenceTransformerEmbedder:
    """실제 사용하는 백엔드."""

    name = EMBED_MODEL
    requires_fit = False

    def __init__(self, model_name: str = EMBED_MODEL):
        from sentence_transformers import SentenceTransformer
        self.model = SentenceTransformer(model_name)
        self.name = model_name
        self.dim = self.model.get_sentence_embedding_dimension()

    def encode(self, texts, batch_size: int = 32) -> np.ndarray:
        if isinstance(texts, str):
            texts = [texts]
        vec = self.model.encode(
            list(texts),
            batch_size=batch_size,
            normalize_embeddings=True,
            convert_to_numpy=True,
            show_progress_bar=len(texts) > 200,
        )
        return np.asarray(vec, dtype="float32")


class HashingEmbedder:
    """모델 다운로드 없이 쓰는 대체 백엔드.

    문자 n-gram TF-IDF 를 SVD 로 축소한다.
    표기가 겹치는 문장끼리 가까워지는 성질만 있고 의미를 이해하지 않는다.
    배선과 자료구조를 점검하는 용도로만 쓴다.
    """

    name = "hashing-tfidf-svd (테스트 전용)"
    requires_fit = True

    def __init__(self, dim: int = 256):
        from sklearn.decomposition import TruncatedSVD
        from sklearn.feature_extraction.text import TfidfVectorizer
        self.dim = dim
        self._tfidf = TfidfVectorizer(analyzer="char_wb", ngram_range=(2, 4), min_df=1)
        self._svd = TruncatedSVD(n_components=dim, random_state=0)
        self._fitted = False

    def fit(self, corpus):
        x = self._tfidf.fit_transform(list(corpus))
        n_comp = min(self.dim, x.shape[1] - 1, max(2, x.shape[0] - 1))
        self._svd.n_components = n_comp
        self._svd.fit(x)
        self.dim = n_comp
        self._fitted = True
        return self

    def encode(self, texts, batch_size: int = 32) -> np.ndarray:
        if not self._fitted:
            raise RuntimeError("HashingEmbedder 는 fit(corpus) 을 먼저 호출해야 합니다.")
        if isinstance(texts, str):
            texts = [texts]
        x = self._tfidf.transform(list(texts))
        return l2_normalize(self._svd.transform(x))


def get_embedder(backend: str = "auto"):
    """
    backend
      'auto'    모델을 불러오고, 실패하면 이유를 알려주며 중단
      'st'      SentenceTransformer 강제
      'hashing' 테스트용 대체 백엔드 강제
    """
    if backend == "hashing":
        return HashingEmbedder()

    try:
        return SentenceTransformerEmbedder()
    except Exception as e:
        msg = (
            f"임베딩 모델 '{EMBED_MODEL}' 을 불러오지 못했습니다. ({type(e).__name__}: {e})\n"
            "확인할 것\n"
            "  1) pip install sentence-transformers\n"
            "  2) 네트워크에서 huggingface.co 접근 가능 여부\n"
            "  3) 오프라인이면 모델을 미리 받아 MOVAR_EMBED_MODEL 에 로컬 경로 지정\n"
            "배선 점검만 하려면 backend='hashing' 을 쓰십시오. 검색 품질 평가에는 쓸 수 없습니다."
        )
        if backend == "auto":
            raise RuntimeError(msg) from e
        raise


if __name__ == "__main__":
    print(f"설정된 모델: {EMBED_MODEL} (dim {EMBED_DIM})")
    try:
        emb = get_embedder("auto")
        v = emb.encode(["탈모 관리 샴푸", "비듬 관리 샴푸"])
        print("로드 성공", emb.name, v.shape, "norm", np.linalg.norm(v, axis=1))
    except RuntimeError as e:
        print("로드 실패\n", e)

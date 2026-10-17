import { useEffect, useState } from 'react'
import { getProductRecommendations } from '../services/productRecommendations'
import type { HaircareProduct, RecommendationResponse } from '../services/productRecommendations'
import './ProductRecommendations.css'

function ProductImage({ product }: { product: HaircareProduct }) {
  const [failed, setFailed] = useState(false)
  return (
    <div className="haircare-image">
      {product.imageUrl && !failed ? (
        <img src={product.imageUrl} alt={product.name} loading="lazy" onError={() => setFailed(true)} />
      ) : <span>상품 이미지 준비 중</span>}
    </div>
  )
}

export default function ProductRecommendations() {
  const [response, setResponse] = useState<RecommendationResponse | null>(null)
  const [error, setError] = useState(false)
  const [attempt, setAttempt] = useState(0)

  useEffect(() => {
    let active = true
    getProductRecommendations().then(result => {
      if (active) setResponse(result)
    }).catch(() => {
      if (active) setError(true)
    })
    return () => { active = false }
  }, [attempt])

  return (
    <section className="card product-card haircare-recommendations" aria-labelledby="haircare-heading">
      <h2 id="haircare-heading">헤어케어 상품 추천</h2>
      <div aria-live="polite">
        {error ? (
          <div className="haircare-message">
            <p>상품을 불러오지 못했어요.</p>
            <button type="button" onClick={() => { setError(false); setResponse(null); setAttempt(n => n + 1) }}>다시 시도</button>
          </div>
        ) : !response ? <p className="haircare-message">상품을 불러오는 중이에요.</p> : (
          <>
            <p className="haircare-caption">{response.mode === 'demo' ? '데모 상품 · 맞춤 추천 전' : '나의 두피에 맞춘 추천 상품'}</p>
            {response.products.length === 0 ? <p className="haircare-message">표시할 상품이 없어요.</p> : (
              <ul className="haircare-list">
                {response.products.map(product => (
                  <li key={product.id} className="haircare-item">
                    <ProductImage key={product.imageUrl} product={product} />
                    <div className="haircare-info">
                      <span className="haircare-brand">{product.brand}</span>
                      <h3 className="haircare-name">{product.name}</h3>
                      <strong>{product.price === null ? '가격 정보 없음' : `${product.price.toLocaleString('ko-KR')}원`}</strong>
                      {/^https?:\/\//i.test(product.productUrl) && <a href={product.productUrl} target="_blank" rel="noopener noreferrer" aria-label={`${product.name} 상품 보기 (새 창)`}>상품 보기 ↗</a>}
                    </div>
                  </li>
                ))}
              </ul>
            )}
            {response.mode === 'demo' && <p className="haircare-footnote">등록된 상품 중 임의로 표시합니다. 가격은 수집 당시 기준이며 판매처에서 달라질 수 있어요.</p>}
          </>
        )}
      </div>
    </section>
  )
}

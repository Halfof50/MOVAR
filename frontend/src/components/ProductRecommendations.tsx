import { useEffect, useState } from 'react'
import { getProductRecommendations } from '../services/productRecommendations'
import type { HaircareProduct } from '../services/productRecommendations'
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

export function ProductList({ products }: { products: HaircareProduct[] }) {
  if (products.length === 0) return <p className="haircare-message">조건에 맞는 상품을 찾지 못했어요.</p>
  return (
    <ul className="haircare-list">
      {products.map(product => (
        <li key={product.id} className="haircare-item">
          <ProductImage key={product.imageUrl} product={product} />
          <div className="haircare-info">
            {product.brand && <span className="haircare-brand">{product.brand}</span>}
            <h3 className="haircare-name">{product.name}</h3>
            <strong>{product.price === null ? '가격 정보 없음' : `${product.price.toLocaleString('ko-KR')}원`}</strong>
            {product.note && <p className="haircare-note">{product.note}</p>}
            {/^https?:\/\//i.test(product.productUrl) && <a href={product.productUrl} target="_blank" rel="noopener noreferrer" aria-label={`${product.name} 상품 보기 (새 창)`}>상품 보기 ↗</a>}
          </div>
        </li>
      ))}
    </ul>
  )
}

// Shows the products recommended in the user's latest saved analysis.
export default function ProductRecommendations({ analysisId }: { analysisId?: string }) {
  const [state, setState] = useState<{ id: string; products: HaircareProduct[] | null; failed: boolean } | null>(null)
  const [attempt, setAttempt] = useState(0)

  useEffect(() => {
    if (!analysisId) return
    let active = true
    getProductRecommendations(analysisId).then(products => {
      if (active) setState({ id: analysisId, products, failed: false })
    }).catch(() => {
      if (active) setState({ id: analysisId, products: null, failed: true })
    })
    return () => { active = false }
  }, [analysisId, attempt])

  const current = analysisId && state?.id === analysisId ? state : null
  return (
    <section className="card product-card haircare-recommendations" aria-labelledby="haircare-heading">
      <h2 id="haircare-heading">헤어케어 상품 추천</h2>
      <div aria-live="polite">
        {!analysisId ? <p className="haircare-message">두피를 분석하면 나에게 맞는 상품을 추천해 드려요.</p>
          : !current ? <p className="haircare-message">상품을 불러오는 중이에요.</p>
          : current.failed ? (
            <div className="haircare-message">
              <p>상품을 불러오지 못했어요.</p>
              <button type="button" onClick={() => { setState(null); setAttempt(n => n + 1) }}>다시 시도</button>
            </div>
          ) : (
            <>
              <p className="haircare-caption">나의 두피에 맞춘 추천 상품</p>
              <ProductList products={current.products ?? []} />
            </>
          )}
      </div>
    </section>
  )
}

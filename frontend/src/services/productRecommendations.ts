import { demoProducts } from '../data/products'

export interface HaircareProduct {
  id: string
  name: string
  brand: string
  price: number | null
  imageUrl: string
  productUrl: string
}

export interface RecommendationResponse {
  mode: 'demo' | 'personalized'
  products: HaircareProduct[]
}

// Replace this implementation with the future API adapter; keep the UI contract.
// Fetch errors should reject, rather than silently present demo data as personalized.
export async function getProductRecommendations(): Promise<RecommendationResponse> {
  // CSV brand_name maps to brand. Exclude missing, blank and literal NULL values.
  const eligible = demoProducts.filter(product =>
    typeof product.brand === 'string' &&
    product.brand.trim() !== '' &&
    product.brand.trim().toUpperCase() !== 'NULL',
  )
  const pool = [...new Map(eligible.map(p => [p.id, p])).values()]
  for (let i = pool.length - 1; i > 0; i--) {
    const j = Math.floor(Math.random() * (i + 1))
    ;[pool[i], pool[j]] = [pool[j], pool[i]]
  }
  return { mode: 'demo', products: pool.slice(0, 2) }
}

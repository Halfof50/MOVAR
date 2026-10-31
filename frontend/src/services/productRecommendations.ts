import { api } from './api'
import type { AnalysisView, RecommendedProduct } from './api'

export interface HaircareProduct {
  id: string
  name: string
  brand: string
  price: number | null
  imageUrl: string
  productUrl: string
  // Why this product suits the user: the report's personalised sentence, else the model's reason.
  note?: string
}

export function toHaircareProduct(product: RecommendedProduct, note?: string): HaircareProduct {
  return {
    id: String(product.product_id), name: product.product_name, brand: product.brand ?? '',
    price: product.price, imageUrl: product.image ?? '', productUrl: product.link ?? '',
    note: note || product.reason || undefined,
  }
}

export function productsOf(view: AnalysisView): HaircareProduct[] {
  const notes = new Map(view.report.products.map(item => [item.product_id, item.description]))
  return view.recommendations.map(product => toHaircareProduct(product, notes.get(product.product_id)))
}

// Fetch errors reject; sample data is never presented as a personalised recommendation.
export async function getProductRecommendations(analysisId: string): Promise<HaircareProduct[]> {
  return productsOf(await api.getAnalysis(analysisId))
}

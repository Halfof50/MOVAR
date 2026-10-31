import { isLocalAuth } from './authMode'
import { supabase } from './supabase'

// Backend base URL. By default the browser calls /api on the page's own address and the Vite dev server forwards it
// to the backend on this PC (see vite.config.ts). Set VITE_API_BASE_URL only to call a backend directly.
export const API_BASE = (import.meta.env.VITE_API_BASE_URL || '/api').replace(/\/+$/, '')

export type SymptomKey = 'micro_keratin' | 'excess_sebum' | 'follicular_erythema' | 'follicular_pustule' | 'dandruff' | 'hair_loss'
// Result item ids used by the screens -> backend symptom keys.
export const SYMPTOM_KEY: Record<string, SymptomKey> = {
  flakes: 'micro_keratin', sebum: 'excess_sebum', redness: 'follicular_erythema',
  pustules: 'follicular_pustule', dandruff: 'dandruff', hairloss: 'hair_loss',
}
export type Category = 'shampoo' | 'scaler' | 'treatment' | 'tonic'
export const CATEGORY_LABELS: Record<Category, string> = { shampoo: '샴푸', scaler: '스케일러', treatment: '트리트먼트', tonic: '토닉' }

export type RecommendedProduct = {
  rank: number; product_id: number; product_name: string; brand: string | null
  category: string | null; category_kr: string | null; price: number | null; rating: number | null
  reviews: number | null; image: string | null; link: string | null; volume: string | null
  reason: string | null; matched_symptoms: string[]
}
export type Report = {
  analyzed_at: string; care_score: number | null; headline: string; headline_text: string; summary: string
  conditions: { code: string; label: string; level: number; description: string }[]
  care_guides: { title: string; description: string }[]
  routine: { morning: string[]; evening: string[] }
  products: { product_id: number; product_name: string; brand_name: string | null; description: string }[]
  disclaimer: string
}
export type AnalysisView = { symptoms: Record<string, number>; recommendations: RecommendedProduct[]; report: Report }
export type AnalysisResult = AnalysisView & { analysis_id: number | null }
export type StoredAnalysis = AnalysisView & { analysis_id: number; analyzed_at: string; care_score: number | null }
export type HistoryItem = {
  analysis_id: number; analyzed_at: string; care_score: number | null
  symptoms: Record<string, number>; headline: string; changes: Record<string, number> | null
}
export type Question = { id: string; label: string; type: 'single' | 'multi'; options: { value: string; label: string }[] }
export type Answers = Record<string, string | string[]>
export type Hospital = {
  name: string; category: string | null; address: string | null; road_address: string | null
  phone: string | null; distance_m: number | null; lat: number; lng: number; place_url: string | null
}

export class ApiError extends Error {
  code: string
  status: number
  constructor(message: string, code: string, status: number) {
    super(message)
    this.code = code
    this.status = status
  }
}

async function authHeader(): Promise<Record<string, string>> {
  // Only a real Supabase session has a token the backend can verify. Local demo accounts are guests there.
  if (isLocalAuth || !supabase) return {}
  const { data } = await supabase.auth.getSession()
  return data.session ? { Authorization: `Bearer ${data.session.access_token}` } : {}
}

async function request<T>(path: string, init: RequestInit = {}): Promise<T> {
  let response: Response
  try {
    response = await fetch(`${API_BASE}${path}`, { ...init, headers: { ...(await authHeader()), ...init.headers } })
  } catch (error) {
    if (error instanceof DOMException && error.name === 'AbortError') throw error
    throw new ApiError('서버에 연결하지 못했어요. 서버가 켜져 있는지 확인한 뒤 다시 시도해주세요.', 'NETWORK', 0)
  }
  if (!response.ok) {
    const body: unknown = await response.json().catch(() => null)
    const detail = body && typeof body === 'object' && 'detail' in body ? (body as { detail: unknown }).detail : null
    if (detail && typeof detail === 'object' && !Array.isArray(detail) && 'message' in detail)
      throw new ApiError(String((detail as { message: unknown }).message), String((detail as { code?: unknown }).code ?? 'ERROR'), response.status)
    throw new ApiError(response.status === 422 ? '입력값을 확인해주세요.' : '요청을 처리하지 못했어요. 잠시 후 다시 시도해주세요.', 'ERROR', response.status)
  }
  return response.json() as Promise<T>
}

export const api = {
  questionnaire: () => request<Question[]>('/questionnaire'),
  analyze(file: Blob, name: string, options: { categories: Category[]; answers: Answers; signal?: AbortSignal }) {
    const form = new FormData()
    form.append('file', file, name)
    options.categories.forEach(category => form.append('categories', category))
    if (Object.keys(options.answers).length) form.append('questionnaire', JSON.stringify(options.answers))
    return request<AnalysisResult>('/analysis-reports', { method: 'POST', body: form, signal: options.signal })
  },
  listAnalyses: (limit = 50) => request<{ items: HistoryItem[]; total: number }>(`/analyses?limit=${limit}`),
  getAnalysis: (id: number | string) => request<StoredAnalysis>(`/analyses/${encodeURIComponent(String(id))}`),
  mockAnalysis: () => request<AnalysisResult>('/analyses/mock', { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: '{}' }),
  // Near a position (nearest first), or by region name when the browser cannot give a position.
  hospitals(params: { lat?: number; lng?: number; region?: string; radius: number; query: '피부과' | '탈모' }) {
    const search = new URLSearchParams({ radius: String(params.radius), query: params.query })
    if (params.lat !== undefined && params.lng !== undefined) { search.set('lat', String(params.lat)); search.set('lng', String(params.lng)) }
    else if (params.region) search.set('region', params.region)
    return request<{ items: Hospital[]; total: number }>(`/hospitals?${search}`)
  },
}

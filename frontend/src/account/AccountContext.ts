import { createContext, useContext } from 'react'
import type { AnalysisRecord, User } from '../services/accountApi'
export type AccountState = {
  user: User | null; ready: boolean; records: AnalysisRecord[]; historyError: string
  login: (email: string, password: string) => Promise<void>
  logout: () => Promise<void>
  refresh: () => Promise<void>
  save: (record: AnalysisRecord) => Promise<void>
  addSamples: () => Promise<void>
}
export const AccountContext = createContext<AccountState | null>(null)
export function useAccount() {
  const value = useContext(AccountContext)
  if (!value) throw new Error('AccountProvider is missing')
  return value
}
export function errorMessage(error: unknown) {
  return error instanceof Error ? error.message : '처리하지 못했어요. 다시 시도해주세요.'
}

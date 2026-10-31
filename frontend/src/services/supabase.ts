import { isLocalAuth } from './authMode'
import { createClient } from '@supabase/supabase-js'

const url = import.meta.env.VITE_SUPABASE_URL?.trim()
const key = import.meta.env.VITE_SUPABASE_PUBLISHABLE_KEY?.trim()
export const authConfigError = isLocalAuth ? '' : !url || !key
  ? '로그인 연결 설정이 없어요. 관리자에게 문의해주세요.'
  : !/^https:\/\//.test(url) || !key.startsWith('sb_publishable_')
    ? '로그인 연결 설정을 확인해주세요.' : ''

// Only a public publishable key belongs in the browser. Never use a secret key.
export const supabase = isLocalAuth || authConfigError ? null : createClient(url!, key!, {
  auth: { persistSession: true, autoRefreshToken: true, detectSessionInUrl: true },
})
export function getSupabase() {
  if (!supabase) throw new Error(authConfigError)
  return supabase
}
export function authErrorMessage(error: unknown): string {
  const code = error && typeof error === 'object' && 'code' in error ? error.code : ''
  switch (code) {
    case 'user_already_exists': case 'email_exists': return '이미 등록된 계정이에요. 로그인해주세요.'
    case 'signup_disabled': return '현재 회원가입이 비활성화되어 있어요. 관리자에게 문의해주세요.'
    case 'weak_password': return '비밀번호가 보안 조건에 맞지 않아요. 더 길고 다양한 문자로 입력해주세요.'
    case 'email_address_invalid': return '올바른 이메일 주소를 입력해주세요.'
    case 'email_address_not_authorized': return '인증 메일을 보낼 수 없는 주소예요. 관리자에게 메일 발송 설정 확인을 요청해주세요.'
    case 'otp_expired': return '인증 링크가 만료되었어요. 회원가입 화면에서 인증 메일을 다시 요청해주세요.'
    case 'invalid_credentials': return '이메일 또는 비밀번호가 올바르지 않아요.'
    case 'email_not_confirmed': return '이메일 인증을 완료한 뒤 로그인해주세요.'
    case 'over_request_rate_limit': case 'over_email_send_rate_limit': return '요청이 많아요. 잠시 후 다시 시도해주세요.'
    case 'user_banned': return '이용이 제한된 계정이에요. 관리자에게 문의해주세요.'
    case 'email_provider_disabled': return '이메일 로그인이 비활성화되어 있어요. 관리자에게 문의해주세요.'
  }
  if (error instanceof Error && /invalid login credentials/i.test(error.message))
    return '이메일 또는 비밀번호가 올바르지 않아요.'
  if (error instanceof Error && /email not confirmed/i.test(error.message))
    return '이메일 인증을 완료한 뒤 로그인해주세요.'
  if (error instanceof TypeError || (error instanceof Error && /fetch|network/i.test(error.message)))
    return '서버에 연결하지 못했어요. 인터넷 연결을 확인하고 다시 시도해주세요.'
  return '인증 요청을 처리하지 못했어요. 잠시 후 다시 시도해주세요.'
}

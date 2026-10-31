import type { User } from './accountApi'
import { pbkdf2Sha256 } from './sha256'

type LocalUser = User & { salt: string; passwordHash: string }
type Store = { version: 1; users: LocalUser[]; activeId: string | null }
const key = 'movar.local.auth.v1'
const eventName = 'movar-local-auth-changed'
function read(): Store {
  try {
    const raw = localStorage.getItem(key)
    if (!raw) return { version: 1, users: [], activeId: null }
    const data: Store = JSON.parse(raw)
    if (data.version !== 1 || !Array.isArray(data.users) ||
      !(data.activeId === null || typeof data.activeId === 'string') ||
      data.users.some(user => !user || ['id','name','email','salt','passwordHash'].some(field =>
        typeof user[field as keyof LocalUser] !== 'string'))) throw new Error('Invalid data')
    return data
  } catch { throw new Error('로컬 계정 정보를 읽지 못했어요. 브라우저 저장 설정을 확인해주세요.') }
}
function publicUser(user: LocalUser): User { return { id: user.id, name: user.name, email: user.email } }
function current(): User | null {
  const store = read()
  const user = store.users.find(user => user.id === store.activeId)
  return user ? publicUser(user) : null
}
function write(store: Store) {
  try { localStorage.setItem(key, JSON.stringify(store)) }
  catch { throw new Error('계정을 저장하지 못했어요. 브라우저 저장 공간과 설정을 확인해주세요.') }
  window.dispatchEvent(new Event(eventName))
}
function nickname(value: string) {
  const name = value.trim()
  if (name.length < 2 || name.length > 20 || /[\p{Cc}\p{Cf}]/u.test(name))
    throw new Error('닉네임은 제어 문자 없이 2~20자로 입력해주세요.')
  return name
}
const ITERATIONS = 210000
// crypto.subtle and crypto.randomUUID exist only on HTTPS or localhost. On plain http the same PBKDF2 runs in
// JavaScript, so a hash made on either kind of address verifies on the other.
function randomId(): string {
  if (typeof crypto.randomUUID === 'function') return crypto.randomUUID()
  const bytes = crypto.getRandomValues(new Uint8Array(16))
  bytes[6] = (bytes[6] & 0x0f) | 0x40
  bytes[8] = (bytes[8] & 0x3f) | 0x80
  const hex = Array.from(bytes, value => value.toString(16).padStart(2, '0')).join('')
  return `${hex.slice(0, 8)}-${hex.slice(8, 12)}-${hex.slice(12, 16)}-${hex.slice(16, 20)}-${hex.slice(20)}`
}
async function hash(password: string, salt: string): Promise<string> {
  const secret = new TextEncoder().encode(password), saltBytes = new TextEncoder().encode(salt)
  let bits: Uint8Array
  if (globalThis.crypto?.subtle) {
    const material = await crypto.subtle.importKey('raw', secret, 'PBKDF2', false, ['deriveBits'])
    bits = new Uint8Array(await crypto.subtle.deriveBits({ name: 'PBKDF2', salt: saltBytes, iterations: ITERATIONS, hash: 'SHA-256' }, material, 256))
  } else bits = pbkdf2Sha256(secret, saltBytes, ITERATIONS)
  return Array.from(bits, value => value.toString(16).padStart(2, '0')).join('')
}
// Presentation-only storage. Local data is editable by the browser's owner;
// hashing avoids plaintext passwords, but does not make this real authorization.
export const localAuth = {
  async getSession() { return current() },
  subscribe(listener: (user: User | null) => void) {
    const notify = () => { try { listener(current()) } catch { listener(null) } }
    const storage = (event: StorageEvent) => { if (event.key === key || event.key === null) notify() }
    window.addEventListener(eventName, notify)
    window.addEventListener('storage', storage)
    return () => { window.removeEventListener(eventName, notify); window.removeEventListener('storage', storage) }
  },
  async signUp(emailValue: string, password: string, nameValue: string) {
    const email = emailValue.trim().toLowerCase()
    const name = nickname(nameValue)
    if (!/^[^\s@]+@[^\s@]+\.[^\s@]+$/.test(email)) throw new Error('올바른 이메일 형식으로 입력해주세요.')
    if (password.length < 8) throw new Error('비밀번호는 8자 이상 입력해주세요.')
    if (read().users.some(user => user.email === email)) throw new Error('이 브라우저에 이미 등록된 이메일이에요. 로그인해주세요.')
    const salt = randomId()
    const passwordHash = await hash(password, salt)
    const store = read()
    if (store.users.some(user => user.email === email)) throw new Error('이 브라우저에 이미 등록된 이메일이에요. 로그인해주세요.')
    const user: LocalUser = { id: `local-${randomId()}`, name, email, salt, passwordHash }
    write({ version: 1, users: [...store.users, user], activeId: user.id })
    return true
  },
  async login(email: string, password: string) {
    const user = read().users.find(user => user.email === email.trim().toLowerCase())
    if (!user || await hash(password, user.salt) !== user.passwordHash)
      throw new Error('이메일 또는 비밀번호가 올바르지 않아요.')
    const store = read()
    if (!store.users.some(saved => saved.id === user.id)) throw new Error('계정이 삭제되었어요. 다시 가입해주세요.')
    write({ ...store, activeId: user.id })
    return current()!
  },
  async logout() { write({ ...read(), activeId: null }) },
  async updateNickname(value: string) {
    const name = nickname(value)
    const store = read()
    const user = store.users.find(user => user.id === store.activeId)
    if (!user) throw new Error('로그인이 필요해요.')
    write({ ...store, users: store.users.map(item => item.id === user.id ? { ...item, name } : item) })
    return { ...publicUser(user), name }
  },
}

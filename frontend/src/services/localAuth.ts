import type { User } from './accountApi'

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
async function hash(password: string, salt: string): Promise<string> {
  if (!globalThis.crypto?.subtle) throw new Error('로컬 계정은 localhost 또는 HTTPS 주소에서 이용해주세요.')
  const material = await crypto.subtle.importKey('raw', new TextEncoder().encode(password), 'PBKDF2', false, ['deriveBits'])
  const result = await crypto.subtle.deriveBits({ name: 'PBKDF2', salt: new TextEncoder().encode(salt), iterations: 210000, hash: 'SHA-256' }, material, 256)
  return Array.from(new Uint8Array(result), value => value.toString(16).padStart(2, '0')).join('')
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
    if (!globalThis.crypto?.subtle) throw new Error('로컬 계정은 localhost 또는 HTTPS 주소에서 이용해주세요.')
    const salt = crypto.randomUUID()
    const passwordHash = await hash(password, salt)
    const store = read()
    if (store.users.some(user => user.email === email)) throw new Error('이 브라우저에 이미 등록된 이메일이에요. 로그인해주세요.')
    const user: LocalUser = { id: `local-${crypto.randomUUID()}`, name, email, salt, passwordHash }
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

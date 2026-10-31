import assert from 'node:assert/strict'
import { createServer } from 'vite'
const values = new Map()
let blocked = false
let requests = 0
const storage = { getItem:key=>values.get(key)??null, setItem:(key,value)=>{if(blocked)throw new Error('Quota');values.set(key,value)},removeItem:key=>values.delete(key) }
globalThis.localStorage = storage
globalThis.window = new EventTarget()
globalThis.fetch = async () => { requests++; throw new Error('No network allowed in local demo') }
const server = await createServer({define:{'import.meta.env.VITE_AUTH_MODE':JSON.stringify('local')},server:{middlewareMode:true}})
try {
 const {accountApi} = await server.ssrLoadModule('/src/services/accountApi.ts')
 const {supabase,authConfigError} = await server.ssrLoadModule('/src/services/supabase.ts')
 assert.equal(supabase,null);assert.equal(authConfigError,'')
 const events=[];const unsubscribe=accountApi.subscribe(user=>events.push(user))
 assert.equal(await accountApi.getSession(),null)
 await assert.rejects(accountApi.signUp('bad-email','test-password','민재'),/이메일/)
 await assert.rejects(accountApi.signUp('test@example.com','short','민재'),/8자/)
 await assert.rejects(accountApi.signUp('test@example.com','test-password',' '),/닉네임/)
 assert.equal(await accountApi.signUp('TEST@example.com','test-password',' 민재 '),true)
 const first=await accountApi.getSession();assert.equal(first.name,'민재');assert.equal(first.email,'test@example.com')
 assert.ok(first.id.startsWith('local-'))
 assert.equal(events.at(-1).id,first.id)
 assert.ok(![...values.values()].join('').includes('test-password'))
 await assert.rejects(accountApi.signUp('test@example.com','another-password','중복'),/이미 등록/)
 await accountApi.addSamples(first.id);assert.equal((await accountApi.listAnalyses(first.id)).length,3)
 await accountApi.updateNickname('새닉네임');assert.equal((await accountApi.getSession()).name,'새닉네임')
 blocked=true
 await assert.rejects(accountApi.updateNickname('저장실패'),/저장하지 못/)
 blocked=false
 assert.equal((await accountApi.getSession()).name,'새닉네임')
 await accountApi.logout();assert.equal(await accountApi.getSession(),null);assert.equal(events.at(-1),null)
 await assert.rejects(accountApi.login('test@example.com','wrong'),/비밀번호/)
 await accountApi.login('test@example.com','test-password');assert.equal((await accountApi.getSession()).name,'새닉네임')
 await accountApi.logout()
 await accountApi.signUp('second@example.com','second-password','다른회원')
 const second=await accountApi.getSession();assert.notEqual(second.id,first.id)
 assert.equal((await accountApi.listAnalyses(second.id)).length,0)
 await assert.rejects(accountApi.listAnalyses(first.id),/로그인이 필요/)
 // Simulate another tab logging out through shared localStorage.
 const key='movar.local.auth.v1';const data=JSON.parse(values.get(key));data.activeId=null;values.set(key,JSON.stringify(data))
 const event=new Event('storage');Object.defineProperty(event,'key',{value:key});window.dispatchEvent(event)
 assert.equal(events.at(-1),null)
 await accountApi.login('test@example.com','test-password')
 assert.equal((await accountApi.listAnalyses(first.id)).length,3)
 unsubscribe()
 assert.equal(requests,0)
 console.log('PASS local: signup, immediate session, validation, duplicates, hashed storage, nickname, storage failure, login/logout, account separation, tab notification, zero network requests')
} finally {await server.close()}

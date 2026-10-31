import assert from 'node:assert/strict'
import { createServer } from 'vite'
const values = new Map()
globalThis.localStorage = {getItem:k=>values.get(k)??null,setItem:(k,v)=>values.set(k,v),removeItem:k=>values.delete(k)}
const user = {id:'11111111-1111-4111-8111-111111111111',email:'qa@example.com',aud:'authenticated',role:'authenticated',user_metadata:{name:'QA'},app_metadata:{},created_at:new Date().toISOString()}
const token = [ {alg:'HS256'}, {sub:user.id,exp:Math.floor(Date.now()/1000)+3600} ].map(x=>Buffer.from(JSON.stringify(x)).toString('base64url')).join('.')+'.mock'
globalThis.fetch = async (input,options) => {
 const url=String(input)
 if(url.includes('/signup')) {
  const body=JSON.parse(options.body)
  assert.equal(body.data.display_name,'새회원')
  assert.equal(body.data.full_name,'새회원')
  assert.ok(url.includes('redirect_to='))
  if(body.email==='blocked@example.com') return new Response(JSON.stringify({error_code:'signup_disabled',msg:'Signups not allowed'}),{status:422,headers:{'Content-Type':'application/json'}})
  if(body.email==='auto@example.com') return new Response(JSON.stringify({access_token:token,refresh_token:'mock',expires_in:3600,token_type:'bearer',user}),{status:200,headers:{'Content-Type':'application/json'}})
  return new Response(JSON.stringify({...user,identities:[]}),{status:200,headers:{'Content-Type':'application/json'}})
 }
 if(url.includes('/token')) {
  const body=JSON.parse(options.body)
  if(body.password==='wrong')return new Response(JSON.stringify({code:'invalid_credentials',msg:'Invalid login credentials'}),{status:400,headers:{'Content-Type':'application/json'}})
  return new Response(JSON.stringify({access_token:token,refresh_token:'mock',expires_in:3600,token_type:'bearer',user}),{status:200,headers:{'Content-Type':'application/json'}})
 }
 if(url.includes('/user')) {
  assert.equal(options.method,'PUT')
  const body=JSON.parse(options.body)
  assert.deepEqual(Object.keys(body.data).sort(),['display_name','full_name'])
  if(body.data.display_name==='실패테스트') return new Response(JSON.stringify({msg:'Service unavailable'}),{status:503,headers:{'Content-Type':'application/json'}})
  user.user_metadata={...user.user_metadata,...body.data}
  return new Response(JSON.stringify(user),{status:200,headers:{'Content-Type':'application/json'}})
 }
 if(url.includes('/logout'))return new Response(null,{status:204})
 throw new Error('Unexpected network call: '+url)
}
const server=await createServer({define: {'import.meta.env.VITE_AUTH_MODE': JSON.stringify('supabase')}, server:{middlewareMode:true}})
try {
 const {accountApi}=await server.ssrLoadModule('/src/services/accountApi.ts')
 const {supabase}=await server.ssrLoadModule('/src/services/supabase.ts')
 const events=[];const {data}=supabase.auth.onAuthStateChange(event=>events.push(event))
 assert.equal(await accountApi.getSession(),null)
 await assert.rejects(accountApi.login(user.email,'wrong'),/이메일 또는 비밀번호/)
 assert.equal((await accountApi.login(user.email,'correct')).id,user.id)
 assert.equal((await accountApi.getSession()).email,user.email)
 await accountApi.addSamples(user.id)
 assert.equal((await accountApi.listAnalyses(user.id)).length,3)
 await assert.rejects(accountApi.listAnalyses('another-user'),/로그인이 필요/)
 await assert.rejects(accountApi.updateNickname(' '),/2~20자/)
 await assert.rejects(accountApi.updateNickname('가'.repeat(21)),/2~20자/)
 await assert.rejects(accountApi.updateNickname('민\n재'),/제어 문자/)
 assert.equal((await accountApi.updateNickname('  민재  ')).name,'민재')
 assert.equal((await accountApi.getSession()).name,'민재')
 assert.equal(user.user_metadata.display_name,'민재')
 assert.equal(user.user_metadata.full_name,'민재')
 assert.equal(user.user_metadata.name,'QA')
 assert.equal((await accountApi.listAnalyses(user.id)).length,3)
 await assert.rejects(accountApi.updateNickname('실패테스트'),/저장하지 못했어요/)
 assert.equal((await accountApi.getSession()).name,'민재')
 assert.ok(events.includes('USER_UPDATED'))
 await accountApi.logout()
 assert.equal(await accountApi.getSession(),null)
 await assert.rejects(accountApi.updateNickname('민재'),/로그인이 필요/ )
 await assert.rejects(accountApi.listAnalyses(user.id),/로그인이 필요/)
 assert.ok(events.includes('SIGNED_IN'));assert.ok(events.includes('SIGNED_OUT'))
 globalThis.window={location:{origin:'http://localhost:5173'}}
 await assert.rejects(accountApi.signUp('new@example.com','short','새회원'),/8자/)
 await assert.rejects(accountApi.signUp('new@example.com','valid-password',' '),/2~20자/)
 await assert.rejects(accountApi.signUp('blocked@example.com','valid-password','새회원'),/비활성화/)
 assert.equal(await accountApi.signUp('new@example.com','valid-password','  새회원  '),false)
 assert.equal(await accountApi.getSession(),null)
 assert.equal(await accountApi.signUp('auto@example.com','valid-password','새회원'),true)
 assert.ok(await accountApi.getSession())
 delete globalThis.window
 await accountApi.logout()
 data.subscription.unsubscribe();supabase.auth.stopAutoRefresh()
 console.log('PASS: mocked Auth invalid login, login, session, local demo history, wrong-user denial, logout, auth events, nickname persistence, metadata preservation, validation, failed update, signup metadata, email confirmation pending, immediate signup session, signup validation and failure')
} finally {await server.close()}

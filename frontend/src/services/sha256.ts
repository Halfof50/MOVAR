// PBKDF2-HMAC-SHA256 in plain JavaScript, with a 32-byte output.
// Browsers expose crypto.subtle only on HTTPS or localhost; this gives the same result on plain http.
// It is used only by the local demo accounts and produces exactly the same bytes as crypto.subtle.

const K = new Uint32Array([
  0x428a2f98, 0x71374491, 0xb5c0fbcf, 0xe9b5dba5, 0x3956c25b, 0x59f111f1, 0x923f82a4, 0xab1c5ed5,
  0xd807aa98, 0x12835b01, 0x243185be, 0x550c7dc3, 0x72be5d74, 0x80deb1fe, 0x9bdc06a7, 0xc19bf174,
  0xe49b69c1, 0xefbe4786, 0x0fc19dc6, 0x240ca1cc, 0x2de92c6f, 0x4a7484aa, 0x5cb0a9dc, 0x76f988da,
  0x983e5152, 0xa831c66d, 0xb00327c8, 0xbf597fc7, 0xc6e00bf3, 0xd5a79147, 0x06ca6351, 0x14292967,
  0x27b70a85, 0x2e1b2138, 0x4d2c6dfc, 0x53380d13, 0x650a7354, 0x766a0abb, 0x81c2c92e, 0x92722c85,
  0xa2bfe8a1, 0xa81a664b, 0xc24b8b70, 0xc76c51a3, 0xd192e819, 0xd6990624, 0xf40e3585, 0x106aa070,
  0x19a4c116, 0x1e376c08, 0x2748774c, 0x34b0bcb5, 0x391c0cb3, 0x4ed8aa4a, 0x5b9cca4f, 0x682e6ff3,
  0x748f82ee, 0x78a5636f, 0x84c87814, 0x8cc70208, 0x90befffa, 0xa4506ceb, 0xbef9a3f7, 0xc67178f2,
])
const IV = new Uint32Array([0x6a09e667, 0xbb67ae85, 0x3c6ef372, 0xa54ff53a, 0x510e527f, 0x9b05688c, 0x1f83d9ab, 0x5be0cd19])

const rotr = (x: number, n: number) => (x >>> n) | (x << (32 - n))

// One SHA-256 compression: block is 16 big-endian words, w is a 64-word scratch buffer.
function compress(state: Uint32Array, block: Uint32Array, w: Uint32Array) {
  for (let i = 0; i < 16; i++) w[i] = block[i]
  for (let i = 16; i < 64; i++) {
    const a = w[i - 15], b = w[i - 2]
    w[i] = (w[i - 16] + (rotr(a, 7) ^ rotr(a, 18) ^ (a >>> 3)) + w[i - 7] + (rotr(b, 17) ^ rotr(b, 19) ^ (b >>> 10))) | 0
  }
  let a = state[0], b = state[1], c = state[2], d = state[3], e = state[4], f = state[5], g = state[6], h = state[7]
  for (let i = 0; i < 64; i++) {
    const t1 = (h + (rotr(e, 6) ^ rotr(e, 11) ^ rotr(e, 25)) + ((e & f) ^ (~e & g)) + K[i] + w[i]) | 0
    const t2 = ((rotr(a, 2) ^ rotr(a, 13) ^ rotr(a, 22)) + ((a & b) ^ (a & c) ^ (b & c))) | 0
    h = g; g = f; f = e; e = (d + t1) | 0; d = c; c = b; b = a; a = (t1 + t2) | 0
  }
  state[0] += a; state[1] += b; state[2] += c; state[3] += d; state[4] += e; state[5] += f; state[6] += g; state[7] += h
}

function wordsToBytes(words: Uint32Array): Uint8Array {
  const bytes = new Uint8Array(words.length * 4)
  const view = new DataView(bytes.buffer)
  words.forEach((word, i) => view.setUint32(i * 4, word))
  return bytes
}

// SHA-256 of `data`, continuing from `initial` after `prefixBytes` bytes that were already absorbed.
function digestFrom(initial: Uint32Array, data: Uint8Array, prefixBytes: number): Uint32Array {
  const state = initial.slice()
  const padded = new Uint8Array(Math.ceil((data.length + 9) / 64) * 64)
  padded.set(data)
  padded[data.length] = 0x80
  const view = new DataView(padded.buffer)
  const bits = (prefixBytes + data.length) * 8
  view.setUint32(padded.length - 8, Math.floor(bits / 2 ** 32))
  view.setUint32(padded.length - 4, bits >>> 0)
  const block = new Uint32Array(16), w = new Uint32Array(64)
  for (let offset = 0; offset < padded.length; offset += 64) {
    for (let i = 0; i < 16; i++) block[i] = view.getUint32(offset + i * 4)
    compress(state, block, w)
  }
  return state
}

export function pbkdf2Sha256(password: Uint8Array, salt: Uint8Array, iterations: number): Uint8Array {
  const key = password.length > 64 ? wordsToBytes(digestFrom(IV, password, 0)) : password
  const ipad = new Uint8Array(64).fill(0x36), opad = new Uint8Array(64).fill(0x5c)
  key.forEach((value, i) => { ipad[i] ^= value; opad[i] ^= value })
  const absorb = (pad: Uint8Array) => {
    const state = IV.slice(), block = new Uint32Array(16), view = new DataView(pad.buffer)
    for (let i = 0; i < 16; i++) block[i] = view.getUint32(i * 4)
    compress(state, block, new Uint32Array(64))
    return state
  }
  const inner0 = absorb(ipad), outer0 = absorb(opad)

  // U1 = HMAC(password, salt || INT(1))
  const first = new Uint8Array(salt.length + 4)
  first.set(salt)
  first[salt.length + 3] = 1
  const u = digestFrom(outer0, wordsToBytes(digestFrom(inner0, first, 64)), 64)
  const t = u.slice()

  // U2..Uc: each message is exactly 32 bytes, so every HMAC is two fixed-size compressions.
  const block = new Uint32Array(16), w = new Uint32Array(64), inner = new Uint32Array(8), out = new Uint32Array(8)
  block[8] = 0x80000000
  block[15] = (64 + 32) * 8
  for (let n = 1; n < iterations; n++) {
    inner.set(inner0)
    block.set(u)
    compress(inner, block, w)
    out.set(outer0)
    block.set(inner)
    compress(out, block, w)
    u.set(out)
    for (let i = 0; i < 8; i++) t[i] ^= u[i]
  }
  return wordsToBytes(t)
}

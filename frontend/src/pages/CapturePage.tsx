import { useEffect, useRef, useState } from 'react'
import type { ChangeEvent } from 'react'
import './CapturePage.css'

type Photo = { url: string; name: string; width: number; height: number; size: number }
const MAX_BYTES = 15 * 1024 * 1024

function cameraError(error: unknown) {
  const name = error instanceof DOMException ? error.name : ''
  if (name === 'NotAllowedError') return '카메라 권한이 허용되지 않았어요. 주소창의 사이트 설정에서 카메라 권한을 확인한 뒤 다시 연결해주세요.'
  if (name === 'NotFoundError') return '사용 가능한 카메라가 없어요. 장치를 연결하거나 저장된 이미지를 선택해주세요.'
  if (name === 'NotReadableError') return '카메라를 사용할 수 없어요. 다른 촬영 프로그램을 종료하고 장치 연결을 확인해주세요.'
  if (name === 'OverconstrainedError') return '선택한 장치를 연결할 수 없어요. 카메라 목록을 새로고침해주세요.'
  return '카메라 연결에 실패했어요. 장치와 브라우저 설정을 확인하고 다시 시도해주세요.'
}

export default function CapturePage() {
  const video = useRef<HTMLVideoElement>(null)
  const stream = useRef<MediaStream | null>(null)
  const photoUrl = useRef<string | null>(null)
  const operation = useRef(0)
  const mounted = useRef(false)
  const [devices, setDevices] = useState<MediaDeviceInfo[]>([])
  const [deviceId, setDeviceId] = useState('')
  const [active, setActive] = useState(false)
  const [ready, setReady] = useState(false)
  const [busy, setBusy] = useState(false)
  const [photo, setPhoto] = useState<Photo | null>(null)
  const [error, setError] = useState('')

  function releaseStream() {
    stream.current?.getTracks().forEach(track => track.stop())
    stream.current = null
    if (video.current) video.current.srcObject = null
  }

  useEffect(() => {
    mounted.current = true
    return () => {
      mounted.current = false
      operation.current += 1
      releaseStream()
      if (photoUrl.current) URL.revokeObjectURL(photoUrl.current)
    }
  }, [])

  async function refreshDevices() {
    if (!navigator.mediaDevices?.enumerateDevices) return
    try {
      const list = await navigator.mediaDevices.enumerateDevices()
      if (mounted.current) setDevices(list.filter(item => item.kind === 'videoinput'))
    } catch {
      if (mounted.current) setError('카메라 목록을 가져오지 못했어요. 장치 연결과 권한을 확인해주세요.')
    }
  }

  function stopCamera() {
    operation.current += 1
    releaseStream()
    setActive(false)
    setReady(false)
    setBusy(false)
  }

  async function startCamera() {
    stopCamera()
    setError('')
    if (!window.isSecureContext || !navigator.mediaDevices?.getUserMedia) {
      setError('직접 촬영은 HTTPS 또는 localhost에서 지원되는 브라우저로 이용해주세요. 저장된 이미지 선택은 계속 사용할 수 있어요.')
      return
    }
    const id = ++operation.current
    setBusy(true)
    try {
      const next = await navigator.mediaDevices.getUserMedia({
        audio: false,
        video: deviceId ? { deviceId: { exact: deviceId } } : { facingMode: { ideal: 'environment' } },
      })
      if (!mounted.current || id !== operation.current) {
        next.getTracks().forEach(track => track.stop())
        return
      }
      stream.current = next
      const track = next.getVideoTracks()[0]
      track.addEventListener('ended', () => {
        if (stream.current !== next || !mounted.current) return
        stopCamera()
        setError('카메라 연결이 끊겼어요. 장치를 확인하고 다시 연결해주세요.')
      })
      setDeviceId(track.getSettings().deviceId ?? '')
      setActive(true)
      if (video.current) {
        video.current.srcObject = next
        await video.current.play()
      }
      if (id === operation.current) await refreshDevices()
    } catch (cause) {
      if (mounted.current && id === operation.current) {
        releaseStream()
        setActive(false)
        setReady(false)
        setError(cameraError(cause))
      }
    } finally {
      if (mounted.current && id === operation.current) setBusy(false)
    }
  }

  async function acceptPhoto(blob: Blob, name: string, id: number) {
    const url = URL.createObjectURL(blob)
    try {
      const img = new Image()
      img.src = url
      await img.decode()
      if (!mounted.current || id !== operation.current) {
        URL.revokeObjectURL(url)
        return
      }
      if (!img.naturalWidth || !img.naturalHeight) throw new Error('empty image')
      if (photoUrl.current) URL.revokeObjectURL(photoUrl.current)
      photoUrl.current = url
      setPhoto({ url, name, width: img.naturalWidth, height: img.naturalHeight, size: blob.size })
      releaseStream()
      setActive(false)
      setReady(false)
    } catch {
      URL.revokeObjectURL(url)
      if (mounted.current && id === operation.current) setError('이미지를 읽을 수 없어요. 정상적인 JPG, PNG 또는 WebP 파일을 선택해주세요.')
    } finally {
      if (mounted.current && id === operation.current) setBusy(false)
    }
  }

  function selectFile(event: ChangeEvent<HTMLInputElement>) {
    const file = event.target.files?.[0]
    event.target.value = ''
    if (!file) return
    setError('')
    if (!['image/jpeg', 'image/png', 'image/webp'].includes(file.type)) {
      setError('JPG, PNG, WebP 이미지만 선택할 수 있어요. HEIC 파일은 JPG로 변환해주세요.')
      return
    }
    if (file.size > MAX_BYTES || file.size === 0) {
      setError('파일 크기는 0바이트보다 크고 15MB 이하여야 해요.')
      return
    }
    stopCamera()
    const id = ++operation.current
    setBusy(true)
    void acceptPhoto(file, file.name, id)
  }

  function capture() {
    const element = video.current
    if (!element || !ready || !element.videoWidth) return
    setError('')
    setBusy(true)
    const id = ++operation.current
    const canvas = document.createElement('canvas')
    canvas.width = element.videoWidth
    canvas.height = element.videoHeight
    const context = canvas.getContext('2d')
    if (!context) { setBusy(false); setError('촬영을 처리할 수 없어요. 다시 시도해주세요.'); return }
    context.drawImage(element, 0, 0)
    canvas.toBlob(blob => {
      if (!mounted.current || id !== operation.current) return
      if (!blob) { setBusy(false); setError('사진 생성에 실패했어요. 다시 촬영해주세요.'); return }
      void acceptPhoto(blob, `MOVAR-scalp-${Date.now()}.jpg`, id)
    }, 'image/jpeg', 0.95)
  }

  function removePhoto() {
    if (photoUrl.current) URL.revokeObjectURL(photoUrl.current)
    photoUrl.current = null
    setPhoto(null)
    setError('')
  }

  return (
    <div className="stack capture-page">
      <section className="page-heading">
        <p className="eyebrow">SCALP CAPTURE</p>
        <h1>나의 두피를 확인해 보아요</h1>
        <p>카메라로 촬영하거나, 저장된 두피 사진을 선택하세요.</p>
      </section>
      {error && <div className="capture-error" role="alert">{error}</div>}
      <div className="capture-grid">
        <section className="card capture-panel" aria-labelledby="camera-title">
          <div className="capture-title"><h2 id="camera-title">01 · 두피 촬영</h2><span className="badge">{active ? '카메라 연결됨' : '연결 대기'}</span></div>
          <div className="camera-stage">
            <video ref={video} autoPlay muted playsInline hidden={!active} onLoadedData={() => setReady(true)} aria-label="카메라 실시간 미리보기" />
            {!active && <div className="camera-empty"><span aria-hidden="true">◎</span><strong>두피가 선명하게 보이도록</strong><p>USB 전자현미경 또는 카메라를 연결해주세요.</p></div>}
          </div>
          <label className="device-label" htmlFor="camera-device">촬영 장치</label>
          <div className="device-row">
            <select id="camera-device" value={deviceId} disabled={busy} onChange={event => { stopCamera(); setDeviceId(event.target.value) }}>
              <option value="">기본 카메라</option>
              {devices.map((device, index) => <option key={device.deviceId || index} value={device.deviceId}>{device.label || `카메라 ${index + 1}`}</option>)}
            </select>
            <button className="button capture-secondary" onClick={() => void refreshDevices()} disabled={busy}>목록 새로고침</button>
          </div>
          <div className="capture-actions">
            {!active && <button className="button" onClick={() => void startCamera()} disabled={busy}>{busy ? '처리 중…' : '카메라 연결'}</button>}
            {active && <button className="button" onClick={capture} disabled={!ready || busy}>사진 촬영</button>}
            {(active || busy) && <button className="button capture-secondary" onClick={stopCamera}>연결 중지</button>}
          </div>
          <p className="capture-hint">최초 연결 시 카메라 권한을 허용해주세요. 장치를 변경한 후 ‘카메라 연결’을 누르세요.</p>
        </section>
        <section className="card capture-panel" aria-labelledby="photo-title">
          <div className="capture-title"><h2 id="photo-title">02 · 이미지 확인</h2><span className="badge">{photo ? '사진 준비됨' : '선택 전'}</span></div>
          <div className="photo-stage">
            {photo ? <img src={photo.url} alt="촬영하거나 선택한 두피 사진" /> : <div className="camera-empty"><span aria-hidden="true">＋</span><strong>사진이 이곳에 표시돼요</strong><p>촬영한 사진 또는 선택한 이미지를 확인하세요.</p></div>}
          </div>
          {photo && <p className="photo-meta">{photo.name}<br />{photo.width} × {photo.height}px · {(photo.size / 1024 / 1024).toFixed(2)}MB</p>}
          <label className="file-label" htmlFor="scalp-file">저장된 이미지 선택</label>
          <input id="scalp-file" type="file" accept="image/jpeg,image/png,image/webp" onChange={selectFile} disabled={busy} />
          <p className="capture-hint">JPG · PNG · WebP / 최대 15MB</p>
          {photo && <div className="capture-actions"><a className="button" href={photo.url} download={photo.name}>사진 다운로드</a><button className="button capture-secondary" onClick={removePhoto} disabled={busy}>사진 지우기</button></div>}
          <p className="capture-hint" aria-live="polite">{photo ? '사진이 준비됐어요. 다시 촬영하거나 다른 이미지를 선택해 바꿀 수 있어요.' : '사진을 촬영하거나 이미지를 선택해주세요.'}</p>
        </section>
      </div>
      <section className="notice capture-notice">
        <strong>촬영·이미지 선택 단계까지 사용할 수 있어요.</strong>
        <p>AI 분석은 아직 연결되지 않았어요. 사진은 서버로 전송되지 않으며, 페이지를 나가거나 새로고침하면 사라져요. 보관하려면 사진을 다운로드해주세요.</p>
        <p>USB 전자현미경이 카메라 목록에 나타나지 않으면 전용 프로그램으로 촬영한 사진을 선택해주세요.</p>
      </section>
    </div>
  )
}

import React, { useState, useRef, useEffect } from 'react'
import { useTranslation } from 'react-i18next'
import { aiApi } from '../services/api'
import {
  UploadCloud,
  Image as ImageIcon,
  CheckCircle,
  Loader,
  AlertTriangle,
  Cpu,
  Sparkles,
  Camera,
  X,
  RefreshCw,
  Zap,
} from 'lucide-react'

// ─── Types ────────────────────────────────────────────────────────────────────

interface YoloResult {
  success: boolean
  tray_count: number
  egg_count?: number
  expected_egg_count?: number
  missing_egg_count?: number
  hen_count?: number
  confidence: number
  detections: any[]
  result_image: string
}

interface TrayTypes {
  green_plastic: number
  paper_cardboard: number
  other: number
  unknown: number
}

interface OpenAIResult {
  success: boolean
  egg_count: number
  tray_count: number
  expected_egg_count?: number
  missing_egg_count?: number
  hen_count?: number
  tray_types: TrayTypes
  confidence: 'high' | 'medium' | 'low'
  image_quality: 'good' | 'fair' | 'poor'
  notes: string
}

type AnalysisMode = 'openai' | 'yolo' | 'dual_ai'
type DetectionTarget = 'eggs' | 'hens' | 'trays'

// ─── Helpers ──────────────────────────────────────────────────────────────────

const confidenceColor = (c: string) => {
  if (c === 'high') return '#10b981'
  if (c === 'medium') return '#f59e0b'
  return '#ef4444'
}

const qualityColor = (q: string) => {
  if (q === 'good') return '#10b981'
  if (q === 'fair') return '#f59e0b'
  return '#ef4444'
}

const cap = (s: string) => s.charAt(0).toUpperCase() + s.slice(1)

// ─── Component ────────────────────────────────────────────────────────────────

export default function EggCounterPage() {
  const { t } = useTranslation()
  const [mode, setMode] = useState<AnalysisMode>('openai')
  const [target, setTarget] = useState<DetectionTarget>('trays')
  const [selectedFile, setSelectedFile] = useState<File | null>(null)
  const [previewUrl, setPreviewUrl] = useState<string | null>(null)
  
  const [topFile, setTopFile] = useState<File | null>(null)
  const [topPreviewUrl, setTopPreviewUrl] = useState<string | null>(null)
  const [sideFile, setSideFile] = useState<File | null>(null)
  const [sidePreviewUrl, setSidePreviewUrl] = useState<string | null>(null)
  
  const [activeUploadContext, setActiveUploadContext] = useState<'single' | 'top' | 'side' | 'dual_multi'>('single')
  const [loading, setLoading] = useState(false)
  const [status, setStatus] = useState<string | null>(null)
  const [openaiResult, setOpenaiResult] = useState<OpenAIResult | null>(null)
  const [yoloResult, setYoloResult] = useState<YoloResult | null>(null)
  const [error, setError] = useState<string | null>(null)
  const [threshold, setThreshold] = useState(0.35)
  const [eggCost, setEggCost] = useState<number>(0)
  const [isCameraOpen, setIsCameraOpen] = useState(false)
  const [facingMode, setFacingMode] = useState<'environment' | 'user'>('environment')
  const [cameraLoading, setCameraLoading] = useState(false)
  const [liveStats, setLiveStats] = useState({
    egg_count: 0,
    tray_count: 0,
    hen_count: 0,
    expected_egg_count: 0,
    missing_egg_count: 0,
    confidence: 0,
  })
  const [liveDetections, setLiveDetections] = useState<any[]>([])

  const fileInputRef = useRef<HTMLInputElement>(null)
  const cameraInputRef = useRef<HTMLInputElement>(null)
  const videoRef = useRef<HTMLVideoElement>(null)
  const canvasRef = useRef<HTMLCanvasElement>(null)
  const overlayCanvasRef = useRef<HTMLCanvasElement>(null)
  const streamRef = useRef<MediaStream | null>(null)
  const isDetectingRef = useRef(false)
  const animFrameIdRef = useRef<number | null>(null)
  const lastDetectionsRef = useRef<any[]>([])
  const lastResultImageRef = useRef<string>('')
  const lastStatsRef = useRef(liveStats)
  const targetRef = useRef(target)
  const thresholdRef = useRef(threshold)
  const isCameraOpenRef = useRef(false)

  useEffect(() => {
    targetRef.current = target
  }, [target])

  useEffect(() => {
    thresholdRef.current = threshold
  }, [threshold])

  useEffect(() => {
    return () => {
      stopCamera()
    }
  }, [])

  const stopCameraStreamOnly = () => {
    if (streamRef.current) {
      streamRef.current.getTracks().forEach(track => track.stop())
      streamRef.current = null
    }
    if (videoRef.current) {
      videoRef.current.srcObject = null
    }
  }

  const stopCamera = () => {
    isCameraOpenRef.current = false
    if (animFrameIdRef.current) {
      cancelAnimationFrame(animFrameIdRef.current)
      animFrameIdRef.current = null
    }
    stopCameraStreamOnly()
    setIsCameraOpen(false)
    setCameraLoading(false)
  }

  const getCameraStream = async (desiredFacing: 'environment' | 'user' = 'environment') => {
    if (!navigator.mediaDevices || !navigator.mediaDevices.getUserMedia) {
      throw new Error('Camera access is not supported in this browser. Ensure you are using HTTPS.')
    }

    if (desiredFacing === 'environment') {
      // 1. Try finding back/rear camera via deviceId enumeration
      try {
        const devices = await navigator.mediaDevices.enumerateDevices()
        const videoDevices = devices.filter(d => d.kind === 'videoinput')
        const backDevice = videoDevices.find(d => /back|rear|environment|world|facing back|camera2 0/i.test(d.label))
          || (videoDevices.length > 1 ? videoDevices[videoDevices.length - 1] : null)

        if (backDevice && backDevice.deviceId) {
          try {
            return await navigator.mediaDevices.getUserMedia({
              video: {
                deviceId: { exact: backDevice.deviceId },
                width: { ideal: 1920 },
                height: { ideal: 1080 }
              },
              audio: false
            })
          } catch (e) {
            console.warn('getUserMedia exact deviceId failed, falling back:', e)
          }
        }
      } catch (enumErr) {
        console.warn('enumerateDevices failed:', enumErr)
      }

      // 2. Try exact environment constraint
      try {
        return await navigator.mediaDevices.getUserMedia({
          video: {
            facingMode: { exact: 'environment' },
            width: { ideal: 1920 },
            height: { ideal: 1080 }
          },
          audio: false
        })
      } catch (exactErr) {
        console.warn('exact environment facingMode failed, trying ideal:', exactErr)
      }

      // 3. Try ideal environment
      try {
        return await navigator.mediaDevices.getUserMedia({
          video: {
            facingMode: { ideal: 'environment' },
            width: { ideal: 1280 },
            height: { ideal: 720 }
          },
          audio: false
        })
      } catch (idealErr) {
        console.warn('ideal environment facingMode failed:', idealErr)
      }
    } else {
      // Front camera requested
      try {
        return await navigator.mediaDevices.getUserMedia({
          video: {
            facingMode: 'user',
            width: { ideal: 1280 },
            height: { ideal: 720 }
          },
          audio: false
        })
      } catch (userErr) {
        console.warn('user facingMode failed:', userErr)
      }
    }

    // Fallback to default video
    return await navigator.mediaDevices.getUserMedia({ video: true, audio: false })
  }

  const drawOverlay = () => {
    const video = videoRef.current
    const canvas = overlayCanvasRef.current
    if (!video || !canvas || video.readyState < 2) return

    const displayW = canvas.clientWidth || video.clientWidth
    const displayH = canvas.clientHeight || video.clientHeight
    if (canvas.width !== displayW || canvas.height !== displayH) {
      canvas.width = displayW
      canvas.height = displayH
    }

    const ctx = canvas.getContext('2d')
    if (!ctx) return

    ctx.clearRect(0, 0, displayW, displayH)

    const videoW = video.videoWidth || 640
    const videoH = video.videoHeight || 480

    // Map object-fit: cover coordinates
    const scale = Math.max(displayW / videoW, displayH / videoH)
    const offsetX = (displayW - videoW * scale) / 2
    const offsetY = (displayH - videoH * scale) / 2

    const detections = lastDetectionsRef.current || []

    for (const det of detections) {
      const bbox = det.bbox || []
      if (bbox.length < 4) continue
      const [x1, y1, x2, y2] = bbox

      const sx = x1 * scale + offsetX
      const sy = y1 * scale + offsetY
      const sw = (x2 - x1) * scale
      const sh = (y2 - y1) * scale

      const isTray = (det.class || '').includes('tray')
      const isHen = (det.class || '').includes('hen')

      const boxColor = isTray ? '#06b6d4' : (isHen ? '#ef4444' : '#f59e0b')
      const labelBg = isTray ? 'rgba(6, 182, 212, 0.9)' : (isHen ? 'rgba(239, 68, 68, 0.9)' : 'rgba(245, 158, 11, 0.9)')
      const labelText = isTray
        ? `TRAY #${det.id || 1} (30 Eggs)`
        : (isHen ? `HEN #${det.id || 1}` : `EGG #${det.id || 1} ${Math.round((det.confidence || 0) * 100)}%`)

      ctx.save()
      ctx.shadowColor = boxColor
      ctx.shadowBlur = 8
      ctx.strokeStyle = boxColor
      ctx.lineWidth = Math.max(2, Math.min(4, displayW / 200))

      if (typeof ctx.roundRect === 'function') {
        ctx.beginPath()
        ctx.roundRect(sx, sy, sw, sh, 6)
        ctx.stroke()
      } else {
        ctx.strokeRect(sx, sy, sw, sh)
      }

      // Draw corner brackets
      const bracketLen = Math.min(16, sw / 3, sh / 3)
      ctx.lineWidth = Math.max(3, ctx.lineWidth + 1)
      ctx.beginPath()
      ctx.moveTo(sx, sy + bracketLen)
      ctx.lineTo(sx, sy)
      ctx.lineTo(sx + bracketLen, sy)
      ctx.moveTo(sx + sw - bracketLen, sy)
      ctx.lineTo(sx + sw, sy)
      ctx.lineTo(sx + sw, sy + bracketLen)
      ctx.moveTo(sx, sy + sh - bracketLen)
      ctx.lineTo(sx, sy + sh)
      ctx.lineTo(sx + bracketLen, sy + sh)
      ctx.moveTo(sx + sw - bracketLen, sy + sh)
      ctx.lineTo(sx + sw, sy + sh)
      ctx.lineTo(sx + sw, sy + sh - bracketLen)
      ctx.stroke()

      // Tag Label
      ctx.shadowBlur = 0
      ctx.fillStyle = labelBg
      const fontSize = Math.max(11, Math.min(14, Math.round(displayW / 35)))
      ctx.font = `bold ${fontSize}px sans-serif`
      const textWidth = ctx.measureText(labelText).width
      const tagH = fontSize + 8
      const tagY = sy > tagH + 4 ? sy - tagH - 2 : sy + 4

      ctx.fillRect(sx, tagY, textWidth + 12, tagH)
      ctx.fillStyle = '#ffffff'
      ctx.fillText(labelText, sx + 6, tagY + fontSize + 1)

      ctx.restore()
    }
  }

  const sendFrameForDetection = async () => {
    if (isDetectingRef.current || !isCameraOpenRef.current) return
    const video = videoRef.current
    if (!video || video.readyState < 2 || video.paused || video.ended) return

    isDetectingRef.current = true

    try {
      // Downscale frame to ~640px for ultra-low latency inference
      const origW = video.videoWidth || 640
      const origH = video.videoHeight || 480
      const scale = Math.min(1, 640 / origW)
      const w = Math.round(origW * scale)
      const h = Math.round(origH * scale)

      if (!canvasRef.current) return
      const canvas = canvasRef.current
      canvas.width = w
      canvas.height = h
      const ctx = canvas.getContext('2d')
      if (!ctx) return
      ctx.drawImage(video, 0, 0, w, h)

      const blob = await new Promise<Blob | null>(res => canvas.toBlob(res, 'image/jpeg', 0.65))
      if (!blob) return

      const formData = new FormData()
      formData.append('frame', blob, 'frame.jpg')
      formData.append('confidence_threshold', String(thresholdRef.current))
      formData.append('target', targetRef.current)

      const resp = await aiApi.liveEggDetect(formData)
      const data = resp.data

      if (data && data.success) {
        const normFactor = scale > 0 ? (1 / scale) : 1
        const normalizedDets = (data.detections || []).map((d: any) => {
          if (!d.bbox || d.bbox.length < 4) return d
          return {
            ...d,
            bbox: [
              d.bbox[0] * normFactor,
              d.bbox[1] * normFactor,
              d.bbox[2] * normFactor,
              d.bbox[3] * normFactor,
            ]
          }
        })
        lastDetectionsRef.current = normalizedDets
        if (data.result_image) {
          lastResultImageRef.current = data.result_image
        }
        const newStats = {
          egg_count: data.egg_count || 0,
          tray_count: data.tray_count || 0,
          hen_count: data.hen_count || 0,
          expected_egg_count: data.expected_egg_count || 0,
          missing_egg_count: data.missing_egg_count || 0,
          confidence: data.confidence || 0,
        }
        lastStatsRef.current = newStats
        setLiveStats(newStats)
        setLiveDetections(data.detections || [])
      }
    } catch (err) {
      console.debug('live detect tick error:', err)
    } finally {
      isDetectingRef.current = false
    }
  }

  const startLiveDetectionLoop = () => {
    let lastSendTime = 0
    const SEND_INTERVAL = 280

    const tick = (now: number) => {
      if (!isCameraOpenRef.current) return

      drawOverlay()

      if (now - lastSendTime >= SEND_INTERVAL) {
        lastSendTime = now
        sendFrameForDetection()
      }

      animFrameIdRef.current = requestAnimationFrame(tick)
    }

    animFrameIdRef.current = requestAnimationFrame(tick)
  }

  const startCamera = async (targetFacing: 'environment' | 'user' = 'environment') => {
    setOpenaiResult(null)
    setYoloResult(null)
    setError(null)
    setStatus(null)
    setCameraLoading(true)
    setFacingMode(targetFacing)

    if (!navigator.mediaDevices || !navigator.mediaDevices.getUserMedia) {
      setError('Camera access is not supported in this browser. Ensure you are using HTTPS. Falling back to native camera.')
      cameraInputRef.current?.click()
      setCameraLoading(false)
      return
    }

    try {
      stopCameraStreamOnly()
      const stream = await getCameraStream(targetFacing)
      streamRef.current = stream
      isCameraOpenRef.current = true
      setIsCameraOpen(true)

      setTimeout(() => {
        if (videoRef.current) {
          videoRef.current.srcObject = stream
          videoRef.current.play().catch(e => console.warn('play error:', e))
          videoRef.current.onloadedmetadata = () => {
            setCameraLoading(false)
            startLiveDetectionLoop()
          }
          if (videoRef.current.readyState >= 2) {
            setCameraLoading(false)
            startLiveDetectionLoop()
          }
        }
      }, 150)
    } catch (err: any) {
      console.error('Camera access denied:', err)
      setError('Could not access back camera (' + (err.message || 'Permission denied') + '). Please ensure camera permissions are allowed.')
      setIsCameraOpen(false)
      isCameraOpenRef.current = false
      setCameraLoading(false)
    }
  }

  const handleFlipCamera = async () => {
    const nextFacing = facingMode === 'environment' ? 'user' : 'environment'
    setFacingMode(nextFacing)
    setCameraLoading(true)
    stopCameraStreamOnly()
    try {
      const stream = await getCameraStream(nextFacing)
      streamRef.current = stream
      if (videoRef.current) {
        videoRef.current.srcObject = stream
        await videoRef.current.play().catch(e => console.warn(e))
      }
    } catch (e: any) {
      console.warn('Flip camera failed:', e)
    } finally {
      setCameraLoading(false)
    }
  }

  const capturePhoto = () => {
    const video = videoRef.current
    const canvas = canvasRef.current
    if (!video || !canvas) return

    canvas.width = video.videoWidth || 1280
    canvas.height = video.videoHeight || 720
    const ctx = canvas.getContext('2d')
    if (!ctx) return

    ctx.drawImage(video, 0, 0, canvas.width, canvas.height)
    canvas.toBlob((blob) => {
      if (!blob) return
      const file = new File([blob], `camera_scan_${Date.now()}.jpg`, { type: 'image/jpeg' })

      if (mode === 'dual_ai') {
        if (activeUploadContext === 'top') {
          setTopFile(file)
          setTopPreviewUrl(URL.createObjectURL(file))
        } else {
          setSideFile(file)
          setSidePreviewUrl(URL.createObjectURL(file))
        }
      } else {
        setSelectedFile(file)
        setPreviewUrl(URL.createObjectURL(file))

        const stats = lastStatsRef.current
        setYoloResult({
          success: true,
          tray_count: stats.tray_count,
          egg_count: stats.egg_count,
          expected_egg_count: stats.expected_egg_count,
          missing_egg_count: stats.missing_egg_count,
          hen_count: stats.hen_count,
          confidence: stats.confidence || 0.85,
          detections: lastDetectionsRef.current,
          result_image: lastResultImageRef.current || ''
        })
        setOpenaiResult(null)
        setStatus(`Live Capture Complete! ${stats.egg_count} eggs detected.`)
      }
      stopCamera()
    }, 'image/jpeg', 0.92)
  }

  const handleFileChange = (e: React.ChangeEvent<HTMLInputElement>) => {
    if (e.target.files && e.target.files.length > 0) {
      if (mode === 'dual_ai') {
        if (e.target.files.length >= 2) {
          const top = e.target.files[0]
          const side = e.target.files[1]
          setTopFile(top)
          setTopPreviewUrl(URL.createObjectURL(top))
          setSideFile(side)
          setSidePreviewUrl(URL.createObjectURL(side))
        } else {
          const file = e.target.files[0]
          if (activeUploadContext === 'top') {
            setTopFile(file)
            setTopPreviewUrl(URL.createObjectURL(file))
          } else if (activeUploadContext === 'side') {
            setSideFile(file)
            setSidePreviewUrl(URL.createObjectURL(file))
          } else {
            // Context is 'dual_multi' but only 1 file selected
            if (!topFile) {
              setTopFile(file)
              setTopPreviewUrl(URL.createObjectURL(file))
            } else {
              setSideFile(file)
              setSidePreviewUrl(URL.createObjectURL(file))
            }
          }
        }
      } else {
        const file = e.target.files[0]
        setSelectedFile(file)
        setPreviewUrl(URL.createObjectURL(file))
      }
      setOpenaiResult(null)
      setYoloResult(null)
      setError(null)
      setStatus(null)
      // Reset input so same file can be re-selected
      e.target.value = ''
    }
  }

  const handleAnalyze = async () => {
    if (mode === 'dual_ai' && (!topFile || !sideFile)) return
    if (mode !== 'dual_ai' && !selectedFile) return
    setLoading(true)
    setError(null)
    setStatus('Analyzing image…')

    const formData = new FormData()
    formData.append('target', target)

    try {
      if (mode === 'openai') {
        formData.append('image', selectedFile!, selectedFile!.name)
        const response = await aiApi.analyzeEggImage(formData)
        setOpenaiResult(response.data)
        setYoloResult(null)
      } else if (mode === 'dual_ai') {
        formData.append('top_image', topFile!, topFile!.name)
        formData.append('side_image', sideFile!, sideFile!.name)
        const response = await aiApi.analyzeDualEggImage(formData)
        setOpenaiResult(response.data)
        setYoloResult(null)
      } else {
        formData.append('file', selectedFile!, selectedFile!.name)
        formData.append('confidence_threshold', threshold.toString())
        formData.append('iou_threshold', '0.45')
        const response = await aiApi.countTrays(formData)
        setYoloResult(response.data)
        setOpenaiResult(null)
      }
      setStatus('Analysis complete.')
    } catch (err: any) {
      console.error(err);
      let detail = 'Failed to process image. Please try again.';
      
      if (err.response && err.response.data) {
        if (err.response.data.detail) {
           detail = typeof err.response.data.detail === 'string' ? err.response.data.detail : JSON.stringify(err.response.data.detail);
        } else if (typeof err.response.data === 'string') {
           detail = err.response.data; // e.g. HTML error page
        } else if (err.response.data.message) {
           detail = err.response.data.message;
        } else {
           detail = JSON.stringify(err.response.data);
        }
      } else if (err.message) {
        detail = err.message;
      } else if (typeof err === 'string') {
        detail = err;
      }
      
      setError(detail);
      setStatus(null)
    } finally {
      setLoading(false)
    }
  }

  const hasResult = openaiResult || yoloResult

  return (
    <div className="page-container page-with-bg">
      {/* ─── FULLSCREEN REAL-TIME AI SCANNER VIEW ─────────────────────────── */}
      {isCameraOpen && (
        <div
          className="live-scanner-fullscreen"
          style={{
            position: 'fixed',
            inset: 0,
            zIndex: 999999,
            width: '100vw',
            height: '100vh',
            backgroundColor: '#000000',
            display: 'flex',
            flexDirection: 'column',
            overflow: 'hidden',
          }}
        >
          {/* Main Video Viewport with Overlay Canvas */}
          <div
            style={{
              position: 'relative',
              flex: 1,
              width: '100%',
              height: '100%',
              overflow: 'hidden',
            }}
          >
            <video
              ref={videoRef}
              playsInline
              autoPlay
              muted
              style={{
                width: '100%',
                height: '100%',
                objectFit: 'cover',
                display: 'block',
              }}
            />
            <canvas
              ref={overlayCanvasRef}
              style={{
                position: 'absolute',
                inset: 0,
                width: '100%',
                height: '100%',
                pointerEvents: 'none',
              }}
            />

            {/* Loading Indicator while switching / opening camera */}
            {cameraLoading && (
              <div
                style={{
                  position: 'absolute',
                  inset: 0,
                  display: 'flex',
                  flexDirection: 'column',
                  alignItems: 'center',
                  justifyContent: 'center',
                  background: 'rgba(0,0,0,0.65)',
                  backdropFilter: 'blur(4px)',
                  color: '#ffffff',
                  gap: 12,
                  zIndex: 20,
                }}
              >
                <Loader size={36} className="spinner" />
                <span style={{ fontSize: '1rem', fontWeight: 600 }}>
                  Connecting {facingMode === 'environment' ? 'Back' : 'Front'} Camera...
                </span>
              </div>
            )}

            {/* Top HUD Bar */}
            <div
              style={{
                position: 'absolute',
                top: 0,
                left: 0,
                right: 0,
                padding: '16px 18px',
                display: 'flex',
                alignItems: 'center',
                justifyContent: 'space-between',
                background: 'linear-gradient(180deg, rgba(0,0,0,0.85) 0%, rgba(0,0,0,0.4) 70%, transparent 100%)',
                zIndex: 10,
              }}
            >
              {/* Status Pill */}
              <div style={{ display: 'flex', alignItems: 'center', gap: 8 }}>
                <span
                  style={{
                    display: 'flex',
                    alignItems: 'center',
                    gap: 6,
                    padding: '6px 12px',
                    borderRadius: 20,
                    background: 'rgba(239, 68, 68, 0.25)',
                    border: '1px solid #ef4444',
                    color: '#fca5a5',
                    fontSize: '0.75rem',
                    fontWeight: 700,
                    letterSpacing: '0.5px',
                  }}
                >
                  <span
                    style={{
                      width: 8,
                      height: 8,
                      borderRadius: '50%',
                      background: '#ef4444',
                      boxShadow: '0 0 8px #ef4444',
                    }}
                  />
                  AI LIVE SCANNER
                </span>

                <span
                  style={{
                    padding: '6px 10px',
                    borderRadius: 20,
                    background: 'rgba(255,255,255,0.15)',
                    color: '#ffffff',
                    fontSize: '0.75rem',
                    fontWeight: 600,
                  }}
                >
                  {facingMode === 'environment' ? '📸 Back Cam' : '🤳 Front Cam'}
                </span>
              </div>

              {/* Action Buttons: Flip & Close */}
              <div style={{ display: 'flex', alignItems: 'center', gap: 10 }}>
                <button
                  type="button"
                  onClick={handleFlipCamera}
                  title="Switch Front/Back Camera"
                  style={{
                    width: 44,
                    height: 44,
                    borderRadius: '50%',
                    background: 'rgba(255,255,255,0.2)',
                    backdropFilter: 'blur(8px)',
                    border: '1px solid rgba(255,255,255,0.3)',
                    color: '#ffffff',
                    display: 'flex',
                    alignItems: 'center',
                    justifyContent: 'center',
                    cursor: 'pointer',
                    transition: 'all 0.2s',
                  }}
                >
                  <RefreshCw size={20} />
                </button>

                <button
                  type="button"
                  onClick={stopCamera}
                  title="Close Camera"
                  style={{
                    width: 44,
                    height: 44,
                    borderRadius: '50%',
                    background: 'rgba(239, 68, 68, 0.3)',
                    backdropFilter: 'blur(8px)',
                    border: '1px solid rgba(239, 68, 68, 0.5)',
                    color: '#ffffff',
                    display: 'flex',
                    alignItems: 'center',
                    justifyContent: 'center',
                    cursor: 'pointer',
                    transition: 'all 0.2s',
                  }}
                >
                  <X size={22} />
                </button>
              </div>
            </div>

            {/* Floating Live Detection Stats Pill (Center-Top) */}
            <div
              style={{
                position: 'absolute',
                top: 76,
                left: '50%',
                transform: 'translateX(-50%)',
                zIndex: 10,
                display: 'flex',
                alignItems: 'center',
                gap: 12,
                padding: '8px 18px',
                borderRadius: 24,
                background: 'rgba(15, 23, 42, 0.85)',
                backdropFilter: 'blur(10px)',
                border: '1px solid rgba(245, 158, 11, 0.5)',
                boxShadow: '0 8px 24px rgba(0,0,0,0.5)',
                color: '#ffffff',
              }}
            >
              <div style={{ display: 'flex', alignItems: 'center', gap: 6 }}>
                <span style={{ fontSize: '1.25rem' }}>🥚</span>
                <div>
                  <div style={{ fontSize: '1.1rem', fontWeight: 800, color: '#f59e0b', lineHeight: 1.1 }}>
                    {liveStats.egg_count} Eggs
                  </div>
                  <div style={{ fontSize: '0.65rem', color: '#94a3b8', textTransform: 'uppercase' }}>
                    {liveStats.tray_count > 0 ? `${liveStats.tray_count} Trays Detected` : 'Scanning Live'}
                  </div>
                </div>
              </div>

              {liveStats.confidence > 0 && (
                <div style={{ borderLeft: '1px solid rgba(255,255,255,0.2)', paddingLeft: 12 }}>
                  <div style={{ fontSize: '0.9rem', fontWeight: 700, color: '#10b981' }}>
                    {Math.round(liveStats.confidence * 100)}%
                  </div>
                  <div style={{ fontSize: '0.65rem', color: '#94a3b8' }}>Confidence</div>
                </div>
              )}
            </div>

            {/* Target Mode Quick Switcher (Floating below stats) */}
            <div
              style={{
                position: 'absolute',
                top: 136,
                left: '50%',
                transform: 'translateX(-50%)',
                zIndex: 10,
                display: 'flex',
                gap: 6,
                padding: 4,
                borderRadius: 20,
                background: 'rgba(0,0,0,0.6)',
                backdropFilter: 'blur(6px)',
                border: '1px solid rgba(255,255,255,0.1)',
              }}
            >
              {(['trays', 'eggs', 'hens'] as DetectionTarget[]).map(t => (
                <button
                  key={t}
                  type="button"
                  onClick={() => setTarget(t)}
                  style={{
                    padding: '4px 12px',
                    borderRadius: 16,
                    border: 'none',
                    fontSize: '0.75rem',
                    fontWeight: target === t ? 700 : 500,
                    background: target === t ? 'var(--brand-500, #3b82f6)' : 'transparent',
                    color: target === t ? '#fff' : '#cbd5e1',
                    cursor: 'pointer',
                    transition: 'all 0.2s',
                  }}
                >
                  {t === 'trays' ? '📦 Trays' : t === 'eggs' ? '🥚 Eggs' : '🐔 Hens'}
                </button>
              ))}
            </div>

            {/* Bottom HUD: Shutter / Capture Button & Controls */}
            <div
              style={{
                position: 'absolute',
                bottom: 0,
                left: 0,
                right: 0,
                padding: '24px 20px 36px 20px',
                display: 'flex',
                flexDirection: 'column',
                alignItems: 'center',
                gap: 12,
                background: 'linear-gradient(0deg, rgba(0,0,0,0.9) 0%, rgba(0,0,0,0.5) 60%, transparent 100%)',
                zIndex: 10,
              }}
            >
              <div style={{ fontSize: '0.85rem', color: '#e2e8f0', textAlign: 'center', textShadow: '0 2px 4px rgba(0,0,0,0.8)' }}>
                Point at egg tray — AI detects continuously in real-time
              </div>

              {/* Shutter Button */}
              <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'center', gap: 24, width: '100%' }}>
                <button
                  type="button"
                  onClick={capturePhoto}
                  style={{
                    width: 76,
                    height: 76,
                    borderRadius: '50%',
                    background: 'rgba(255,255,255,0.3)',
                    border: '4px solid #ffffff',
                    padding: 5,
                    cursor: 'pointer',
                    display: 'flex',
                    alignItems: 'center',
                    justifyContent: 'center',
                    boxShadow: '0 0 20px rgba(255,255,255,0.4)',
                    transition: 'transform 0.15s ease',
                  }}
                >
                  <div
                    style={{
                      width: '100%',
                      height: '100%',
                      borderRadius: '50%',
                      background: '#ffffff',
                      display: 'flex',
                      alignItems: 'center',
                      justifyContent: 'center',
                      color: '#0f172a',
                    }}
                  >
                    <Camera size={26} />
                  </div>
                </button>
              </div>

              <div style={{ fontSize: '0.75rem', color: '#94a3b8', textAlign: 'center' }}>
                Tap Shutter to Capture & Save Count
              </div>
            </div>
          </div>
        </div>
      )}
      <header className="page-header">
        <div style={{ display: 'flex', alignItems: 'center', gap: 12 }}>
          <div className="page-icon-wrapper" style={{ background: 'var(--brand-500)' }}>
            <ImageIcon size={20} color="white" />
          </div>
          <div>
            <h1 className="page-title">{t('eggCounter.title')}</h1>
            <p className="page-subtitle">
              {t('eggCounter.subtitle')}
            </p>
          </div>
        </div>
      </header>

      {/* ─── Settings Bar ───────────────────────────────────────────────── */}
      <div style={{ display: 'flex', flexWrap: 'wrap', gap: 24, marginBottom: 24 }}>
        
        {/* Mode Toggle */}
        <div
          style={{
            display: 'flex',
            gap: 8,
            background: 'var(--bg-elevated)',
            borderRadius: 10,
            padding: 6,
            width: 'fit-content',
            border: '1px solid var(--border-subtle)',
          }}
        >
        <button
          onClick={() => { setMode('openai'); setOpenaiResult(null); setYoloResult(null); setError(null); setStatus(null); }}
          style={{
            display: 'flex',
            alignItems: 'center',
            gap: 6,
            padding: '8px 18px',
            borderRadius: 7,
            border: 'none',
            cursor: 'pointer',
            fontWeight: 600,
            fontSize: '0.875rem',
            transition: 'all 0.2s',
            background: mode === 'openai' ? 'var(--brand-500)' : 'transparent',
            color: mode === 'openai' ? '#fff' : 'var(--text-secondary)',
          }}
        >
          <Sparkles size={15} />
          {t('eggCounter.aiVisionBtn')}
        </button>
        <button
          onClick={() => { setMode('dual_ai'); setOpenaiResult(null); setYoloResult(null); setError(null); setStatus(null); setTarget('trays'); }}
          style={{
            display: 'flex',
            alignItems: 'center',
            gap: 6,
            padding: '8px 18px',
            borderRadius: 7,
            border: 'none',
            cursor: 'pointer',
            fontWeight: 600,
            fontSize: '0.875rem',
            transition: 'all 0.2s',
            background: mode === 'dual_ai' ? 'var(--brand-500)' : 'transparent',
            color: mode === 'dual_ai' ? '#fff' : 'var(--text-secondary)',
          }}
        >
          <Sparkles size={15} />
          Dual View
        </button>
      </div>

      {/* Target Toggle */}
      <div
        style={{
          display: 'flex',
          gap: 8,
          background: 'var(--bg-elevated)',
          borderRadius: 10,
          padding: 6,
          width: 'fit-content',
          border: '1px solid var(--border-subtle)',
        }}
      >
        {(['eggs', 'hens', 'trays'] as DetectionTarget[]).map((targetOption) => (
          <button
            key={targetOption}
            onClick={() => { setTarget(targetOption); setOpenaiResult(null); setYoloResult(null); setError(null); setStatus(null); }}
            style={{
              padding: '8px 18px',
              borderRadius: 7,
              border: 'none',
              cursor: 'pointer',
              fontWeight: 600,
              fontSize: '0.875rem',
              transition: 'all 0.2s',
              background: target === targetOption ? 'var(--brand-500)' : 'transparent',
              color: target === targetOption ? '#fff' : 'var(--text-secondary)',
            }}
          >
            {t(`eggCounter.target${targetOption.charAt(0).toUpperCase() + targetOption.slice(1)}` as any)}
          </button>
        ))}
      </div>

      {/* Egg Cost Input */}
      <div
        style={{
          display: 'flex',
          alignItems: 'center',
          gap: 8,
          background: 'var(--bg-elevated)',
          borderRadius: 10,
          padding: '6px 12px',
          width: 'fit-content',
          border: '1px solid var(--border-subtle)',
        }}
      >
        <span style={{ fontSize: '0.875rem', fontWeight: 600, color: 'var(--text-secondary)' }}>
          Cost per Egg (₹):
        </span>
        <input 
          type="number" 
          min="0"
          step="0.5"
          value={eggCost || ''} 
          onChange={(e) => setEggCost(parseFloat(e.target.value) || 0)}
          style={{ 
            width: '80px', 
            padding: '4px 8px', 
            borderRadius: '6px', 
            border: '1px solid var(--border-subtle)',
            background: 'var(--bg-base)',
            color: 'var(--text-primary)'
          }}
          placeholder="0.00"
        />
      </div>
      </div>

      <div
        style={{
          display: 'grid',
          gridTemplateColumns: 'repeat(auto-fit, minmax(300px, 1fr))',
          gap: 24,
        }}
      >
        {/* ─── Upload Section ──────────────────────────────────────────── */}
        <div className="card">
          <h2 style={{ fontSize: '1.1rem', marginBottom: 16 }}>{t('eggCounter.uploadTitle')}</h2>

          {/* Hidden file inputs */}
          <input
            ref={fileInputRef}
            type="file"
            accept="image/jpeg,image/jpg,image/png,image/webp"
            multiple={mode === 'dual_ai'}
            onChange={handleFileChange}
            style={{ display: 'none' }}
          />
          <input
            ref={cameraInputRef}
            type="file"
            accept="image/*"
            capture="environment"
            onChange={handleFileChange}
            style={{ display: 'none' }}
          />

          {/* Hidden helper canvas for frame capture */}
          <canvas ref={canvasRef} style={{ display: 'none' }} />
              {mode === 'dual_ai' ? (
                <div className="dual-ai-grid" style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: 12, marginBottom: 12 }}>
                  <label
                    onClick={() => { setActiveUploadContext('top'); fileInputRef.current?.click(); }}
                    style={{
                      border: '2px dashed var(--brand-500)',
                      borderRadius: 8,
                      padding: 24,
                      display: 'flex',
                      flexDirection: 'column',
                      alignItems: 'center',
                      justifyContent: 'center',
                      cursor: 'pointer',
                      backgroundColor: 'var(--bg-elevated)',
                      transition: 'all 0.2s',
                    }}
                  >
                    <UploadCloud size={32} color="var(--brand-500)" style={{ marginBottom: 12 }} />
                    <span style={{ color: 'var(--text-primary)', fontWeight: 500, textAlign: 'center', fontSize: '0.95rem' }}>
                      Top View
                    </span>
                  </label>
                  <label
                    onClick={() => { setActiveUploadContext('side'); fileInputRef.current?.click(); }}
                    style={{
                      border: '2px dashed var(--brand-500)',
                      borderRadius: 8,
                      padding: 24,
                      display: 'flex',
                      flexDirection: 'column',
                      alignItems: 'center',
                      justifyContent: 'center',
                      cursor: 'pointer',
                      backgroundColor: 'var(--bg-elevated)',
                      transition: 'all 0.2s',
                    }}
                  >
                    <UploadCloud size={32} color="var(--brand-500)" style={{ marginBottom: 12 }} />
                    <span style={{ color: 'var(--text-primary)', fontWeight: 500, textAlign: 'center', fontSize: '0.95rem' }}>
                      Side View
                    </span>
                  </label>
                </div>
              ) : (
                <label
                  onClick={() => { setActiveUploadContext('single'); fileInputRef.current?.click(); }}
                  style={{
                    border: '2px dashed var(--border-color)',
                    borderRadius: 8,
                    padding: 32,
                    display: 'flex',
                    flexDirection: 'column',
                    alignItems: 'center',
                    justifyContent: 'center',
                    cursor: 'pointer',
                    backgroundColor: 'var(--bg-elevated)',
                    transition: 'all 0.2s',
                    marginBottom: 12,
                  }}
                >
                  <UploadCloud size={48} color="var(--text-muted)" style={{ marginBottom: 16 }} />
                  <span
                    style={{
                      color: 'var(--text-primary)',
                      fontWeight: 500,
                      marginBottom: 8,
                      textAlign: 'center',
                    }}
                  >
                    {t('eggCounter.clickToSelect')}
                  </span>
                  <span style={{ color: 'var(--text-muted)', fontSize: '0.85rem' }}>
                    {t('eggCounter.supportedFormats')}
                  </span>
                </label>
              )}

              {/* Live AI Camera Fullscreen Button */}
              <button
                type="button"
                className="btn btn-primary"
                onClick={() => {
                  if (mode === 'dual_ai') {
                    setActiveUploadContext(topFile ? 'side' : 'top');
                  } else {
                    setActiveUploadContext('single');
                  }
                  startCamera('environment');
                }}
                style={{
                  width: '100%',
                  marginBottom: 24,
                  display: 'flex',
                  alignItems: 'center',
                  justifyContent: 'center',
                  gap: 10,
                  padding: '14px 20px',
                  fontSize: '1rem',
                  fontWeight: 600,
                  background: 'linear-gradient(135deg, #10b981 0%, #059669 100%)',
                  boxShadow: '0 4px 14px rgba(16, 185, 129, 0.35)',
                  border: 'none',
                  borderRadius: 10,
                  color: '#ffffff',
                }}
              >
                <Camera size={20} /> Live AI Camera (Full Screen Back Camera) {mode === 'dual_ai' ? (topFile ? '(Side View)' : '(Top View)') : ''}
              </button>

          {mode === 'dual_ai' && (topFile || sideFile) && (
            <div style={{ marginBottom: 24 }}>
              {topFile && (
                <div style={{ marginBottom: 12 }}>
                  <div style={{ fontSize: '0.9rem', color: 'var(--text-muted)', marginBottom: 4 }}>Top View File:</div>
                  <div style={{ fontWeight: 500, wordBreak: 'break-all' }}>{topFile.name}</div>
                </div>
              )}
              {sideFile && (
                <div>
                  <div style={{ fontSize: '0.9rem', color: 'var(--text-muted)', marginBottom: 4 }}>Side View File:</div>
                  <div style={{ fontWeight: 500, wordBreak: 'break-all' }}>{sideFile.name}</div>
                </div>
              )}
            </div>
          )}

          {mode !== 'dual_ai' && selectedFile && (
            <div style={{ marginBottom: 24 }}>
              <div style={{ fontSize: '0.9rem', color: 'var(--text-muted)', marginBottom: 4 }}>
                {t('eggCounter.selectedFile')}
              </div>
              <div style={{ fontWeight: 500, marginBottom: 16, wordBreak: 'break-all' }}>
                {selectedFile.name}
              </div>

              {/* YOLO-only: confidence threshold slider */}
              {mode === 'yolo' && (
                <>
                  <div style={{ fontSize: '0.9rem', color: 'var(--text-muted)', marginBottom: 8 }}>
                    YOLO Confidence Threshold: {Math.round(threshold * 100)}%
                  </div>
                  <input
                    type="range"
                    min="0.1"
                    max="0.9"
                    step="0.05"
                    value={threshold}
                    onChange={(e) => setThreshold(parseFloat(e.target.value))}
                    style={{ width: '100%', marginBottom: 8 }}
                  />
                  <div style={{ fontSize: '0.75rem', color: 'var(--text-muted)' }}>
                    Lowering detects more objects (may include false positives).
                  </div>
                </>
              )}
            </div>
          )}

          <button
            className="btn btn-primary"
            onClick={handleAnalyze}
            disabled={(mode === 'dual_ai' ? (!topFile || !sideFile) : !selectedFile) || loading}
            style={{ width: '100%', padding: '12px 0', fontSize: '1rem' }}
          >
            {loading ? (
              <span
                style={{
                  display: 'flex',
                  alignItems: 'center',
                  gap: 8,
                  justifyContent: 'center',
                }}
              >
                <Loader size={18} className="spinner" />
                Analyzing image…
              </span>
            ) : mode === 'openai' ? (
              <span style={{ display: 'flex', alignItems: 'center', gap: 6, justifyContent: 'center' }}>
                <Sparkles size={16} /> {t('eggCounter.analyzeAIBtn')}
              </span>
            ) : (
              t('eggCounter.detectBtn')
            )}
          </button>

          {/* Status message */}
          {!loading && status && !error && (
            <div
              style={{
                marginTop: 12,
                display: 'flex',
                alignItems: 'center',
                gap: 6,
                fontSize: '0.875rem',
                color: '#10b981',
              }}
            >
              <CheckCircle size={15} /> {status}
            </div>
          )}

          {error && (
            <div
              style={{
                marginTop: 16,
                color: 'var(--danger-500)',
                fontSize: '0.9rem',
                padding: 12,
                backgroundColor: 'rgba(239,68,68,0.1)',
                borderRadius: 6,
              }}
            >
              {error}
            </div>
          )}
        </div>

        {/* ─── Results Section ─────────────────────────────────────────── */}
        <div className="card">
          <h2 style={{ fontSize: '1.1rem', marginBottom: 16 }}>
            {mode === 'openai' ? t('eggCounter.resultTitleAI') : t('eggCounter.resultTitleYOLO')}
          </h2>

          {/* Empty state */}
          {mode !== 'dual_ai' && !previewUrl && !hasResult && (
            <div
              style={{
                display: 'flex',
                alignItems: 'center',
                justifyContent: 'center',
                height: 300,
                backgroundColor: 'var(--bg-elevated)',
                borderRadius: 8,
                color: 'var(--text-muted)',
              }}
            >
              {t('eggCounter.noImage')}
            </div>
          )}
          {mode === 'dual_ai' && !topPreviewUrl && !sidePreviewUrl && !hasResult && (
            <div
              style={{
                display: 'flex',
                alignItems: 'center',
                justifyContent: 'center',
                height: 300,
                backgroundColor: 'var(--bg-elevated)',
                borderRadius: 8,
                color: 'var(--text-muted)',
              }}
            >
              {t('eggCounter.noImage')}
            </div>
          )}

          {/* Preview before analysis */}
          {mode !== 'dual_ai' && previewUrl && !hasResult && !loading && (
            <div>
              <div
                style={{ fontSize: '0.9rem', color: 'var(--text-muted)', marginBottom: 8 }}
              >
                {t('eggCounter.preview')}
              </div>
              <img
                src={previewUrl}
                alt="Preview"
                style={{
                  width: '100%',
                  maxHeight: 400,
                  objectFit: 'contain',
                  borderRadius: 8,
                  border: '1px solid var(--border-subtle)',
                }}
              />
            </div>
          )}

          {mode === 'dual_ai' && (topPreviewUrl || sidePreviewUrl) && !hasResult && !loading && (
            <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: 16 }}>
              {topPreviewUrl && (
                <div>
                  <div style={{ fontSize: '0.9rem', color: 'var(--text-muted)', marginBottom: 8 }}>Top View Preview</div>
                  <img
                    src={topPreviewUrl}
                    alt="Top View Preview"
                    style={{
                      width: '100%',
                      maxHeight: 250,
                      objectFit: 'contain',
                      borderRadius: 8,
                      border: '1px solid var(--border-subtle)',
                    }}
                  />
                </div>
              )}
              {sidePreviewUrl && (
                <div>
                  <div style={{ fontSize: '0.9rem', color: 'var(--text-muted)', marginBottom: 8 }}>Side View Preview</div>
                  <img
                    src={sidePreviewUrl}
                    alt="Side View Preview"
                    style={{
                      width: '100%',
                      maxHeight: 250,
                      objectFit: 'contain',
                      borderRadius: 8,
                      border: '1px solid var(--border-subtle)',
                    }}
                  />
                </div>
              )}
            </div>
          )}

          {/* Loading spinner */}
          {loading && (
            <div
              style={{
                display: 'flex',
                flexDirection: 'column',
                alignItems: 'center',
                justifyContent: 'center',
                height: 300,
                backgroundColor: 'var(--bg-elevated)',
                borderRadius: 8,
                gap: 16,
              }}
            >
              <Loader size={48} className="spinner" color="var(--brand-500)" />
              <div style={{ color: 'var(--text-muted)' }}>
                {mode === 'openai' ? 'Analyzing image with ML model…' : 'Running YOLO Detection…'}
              </div>
            </div>
          )}

          {/* ─── OpenAI structured result ─────────────────────────────── */}
          {openaiResult && (
            <div>
              {/* Confidence warning */}
              {openaiResult.confidence === 'low' && (
                <div
                  style={{
                    display: 'flex',
                    alignItems: 'center',
                    gap: 8,
                    padding: '12px',
                    backgroundColor: 'rgba(239, 68, 68, 0.1)',
                    color: '#ef4444',
                    borderRadius: 6,
                    marginBottom: 16,
                    fontSize: '0.875rem',
                  }}
                >
                  <AlertTriangle size={18} />
                  {t('eggCounter.lowConfidence')}
                </div>
              )}

              {/* Main count cards */}
              <div
                style={{
                  display: 'grid',
                  gridTemplateColumns: target === 'trays' || target === 'eggs' ? '1fr 1fr' : '1fr',
                  gap: 12,
                  marginBottom: 16,
                }}
              >
                {/* Egg count */}
                {(target !== 'hens' || mode === 'dual_ai') && (
                <div
                  style={{
                    backgroundColor: 'rgba(245, 158, 11, 0.1)',
                    padding: '16px',
                    borderRadius: 8,
                    textAlign: 'center',
                    border: '1px solid rgba(245,158,11,0.3)',
                    gridColumn: target === 'eggs' ? '1 / -1' : 'auto',
                  }}
                >
                  <div
                    style={{
                      fontSize: '1.75rem',
                      marginBottom: 4,
                    }}
                  >
                    🥚
                  </div>
                  <div
                    style={{
                      color: '#f59e0b',
                      fontSize: '0.75rem',
                      textTransform: 'uppercase',
                      letterSpacing: '0.5px',
                      marginBottom: 4,
                      fontWeight: 600,
                    }}
                  >
                    {t('eggCounter.eggs')}
                  </div>
                  <div
                    style={{
                      fontSize: '2.5rem',
                      fontWeight: 'bold',
                      color: 'var(--text-primary)',
                      lineHeight: 1,
                    }}
                  >
                    {openaiResult.egg_count}
                  </div>
                  {target === 'trays' && (
                     <div style={{ display: 'flex', flexDirection: 'column', alignItems: 'center', gap: '8px', marginTop: 8 }}>
                       <div style={{ fontSize: '0.8rem', color: 'var(--brand-700)' }}>
                         {t('eggCounter.calculatedTrays', { count: openaiResult.tray_count })}
                       </div>
                       
                       {openaiResult.expected_egg_count !== undefined && openaiResult.expected_egg_count > openaiResult.egg_count && (
                         <div style={{ display: 'flex', gap: '16px', marginTop: '4px' }}>
                           <div style={{ fontSize: '0.9rem', color: 'var(--text-muted)' }}>
                             <span style={{ fontWeight: 500 }}>Expected:</span> {openaiResult.expected_egg_count}
                           </div>
                           <div style={{ fontSize: '0.9rem', color: 'var(--danger-600)', fontWeight: 600 }}>
                             <span style={{ fontWeight: 500 }}>Missing (Deducted):</span> {openaiResult.missing_egg_count}
                           </div>
                         </div>
                       )}
                     </div>
                  )}
                  {eggCost > 0 && openaiResult.egg_count > 0 && (
                     <div style={{ fontSize: '1.2rem', color: '#10b981', marginTop: 12, fontWeight: 700, padding: '8px', backgroundColor: 'rgba(16, 185, 129, 0.1)', borderRadius: '6px' }}>
                       Total Cost: ₹{(openaiResult.egg_count * eggCost).toFixed(2)}
                     </div>
                  )}
                </div>
                )}

                {/* Tray count */}
                {(target === 'trays' || mode === 'dual_ai') && (
                <div
                  style={{
                    backgroundColor: 'rgba(59, 130, 246, 0.1)',
                    padding: '16px',
                    borderRadius: 8,
                    textAlign: 'center',
                    border: '1px solid rgba(59,130,246,0.3)',
                  }}
                >
                  <div style={{ fontSize: '1.75rem', marginBottom: 4 }}>🟢</div>
                  <div
                    style={{
                      color: 'var(--brand-500)',
                      fontSize: '0.75rem',
                      textTransform: 'uppercase',
                      letterSpacing: '0.5px',
                      marginBottom: 4,
                      fontWeight: 600,
                    }}
                  >
                    {t('eggCounter.eggTrays')}
                  </div>
                  <div
                    style={{
                      fontSize: '2.5rem',
                      fontWeight: 'bold',
                      color: 'var(--text-primary)',
                      lineHeight: 1,
                    }}
                  >
                    {openaiResult.tray_count}
                  </div>
                </div>
                )}

                {/* Hen count */}
                {target === 'hens' && (
                <div
                  style={{
                    backgroundColor: 'rgba(239, 68, 68, 0.1)',
                    padding: '16px',
                    borderRadius: 8,
                    textAlign: 'center',
                    border: '1px solid rgba(239,68,68,0.3)',
                    gridColumn: '1 / -1',
                  }}
                >
                  <div style={{ fontSize: '1.75rem', marginBottom: 4 }}>🐔</div>
                  <div
                    style={{
                      color: 'var(--danger-500)',
                      fontSize: '0.75rem',
                      textTransform: 'uppercase',
                      letterSpacing: '0.5px',
                      marginBottom: 4,
                      fontWeight: 600,
                    }}
                  >
                    {t('eggCounter.hens')}
                  </div>
                  <div
                    style={{
                      fontSize: '2.5rem',
                      fontWeight: 'bold',
                      color: 'var(--text-primary)',
                      lineHeight: 1,
                    }}
                  >
                    {openaiResult.hen_count ?? 0}
                  </div>
                </div>
                )}
              </div>

              {/* Confidence + Image Quality badges */}
              <div
                style={{
                  display: 'flex',
                  gap: 10,
                  marginBottom: 16,
                  flexWrap: 'wrap',
                }}
              >
                <span
                  style={{
                    background: `${confidenceColor(openaiResult.confidence)}20`,
                    color: confidenceColor(openaiResult.confidence),
                    border: `1px solid ${confidenceColor(openaiResult.confidence)}40`,
                    borderRadius: 6,
                    padding: '4px 10px',
                    fontSize: '0.8rem',
                    fontWeight: 600,
                  }}
                >
                  {t('eggCounter.confidence', { level: cap(openaiResult.confidence) })}
                </span>
                <span
                  style={{
                    background: `${qualityColor(openaiResult.image_quality)}20`,
                    color: qualityColor(openaiResult.image_quality),
                    border: `1px solid ${qualityColor(openaiResult.image_quality)}40`,
                    borderRadius: 6,
                    padding: '4px 10px',
                    fontSize: '0.8rem',
                    fontWeight: 600,
                  }}
                >
                  {t('eggCounter.quality', { level: cap(openaiResult.image_quality) })}
                </span>
              </div>

              {/* Tray type breakdown */}
              {openaiResult.tray_count > 0 && (
                <div
                  style={{
                    backgroundColor: 'var(--bg-elevated)',
                    borderRadius: 8,
                    padding: 14,
                    marginBottom: 14,
                    border: '1px solid var(--border-subtle)',
                  }}
                >
                  <div
                    style={{
                      fontSize: '0.8rem',
                      fontWeight: 600,
                      color: 'var(--text-muted)',
                      textTransform: 'uppercase',
                      letterSpacing: '0.5px',
                      marginBottom: 10,
                    }}
                  >
                    {t('eggCounter.breakdown')}
                  </div>
                  {[
                    { label: t('eggCounter.greenPlastic'), key: 'green_plastic' },
                    { label: t('eggCounter.paperCardboard'), key: 'paper_cardboard' },
                    { label: t('eggCounter.other'), key: 'other' },
                    { label: t('eggCounter.unknown'), key: 'unknown' },
                  ].map(({ label, key }) => {
                    const count = openaiResult.tray_types[key as keyof TrayTypes]
                    return (
                      <div
                        key={key}
                        style={{
                          display: 'flex',
                          justifyContent: 'space-between',
                          alignItems: 'center',
                          padding: '5px 0',
                          fontSize: '0.875rem',
                          borderBottom: '1px solid var(--border-subtle)',
                        }}
                      >
                        <span style={{ color: 'var(--text-secondary)' }}>{label}</span>
                        <span
                          style={{
                            fontWeight: 700,
                            color: count > 0 ? 'var(--text-primary)' : 'var(--text-muted)',
                          }}
                        >
                          {count}
                        </span>
                      </div>
                    )
                  })}
                </div>
              )}

              {/* Notes */}
              {openaiResult.notes && (
                <div
                  style={{
                    fontSize: '0.85rem',
                    color: 'var(--text-secondary)',
                    backgroundColor: 'var(--bg-elevated)',
                    borderRadius: 6,
                    padding: '10px 14px',
                    borderLeft: '3px solid var(--brand-500)',
                    lineHeight: 1.6,
                  }}
                >
                  <strong style={{ display: 'block', marginBottom: 4, color: 'var(--text-primary)' }}>
                    {t('eggCounter.notes')}
                  </strong>
                  {openaiResult.notes}
                </div>
              )}

              {/* Preview image */}
              {mode !== 'dual_ai' && previewUrl && (
                <div style={{ marginTop: 16 }}>
                  <div
                    style={{ fontSize: '0.9rem', color: 'var(--text-muted)', marginBottom: 8 }}
                  >
                    {t('eggCounter.uploadedImage')}
                  </div>
                  <img
                    src={previewUrl}
                    alt="Analyzed"
                    style={{
                      width: '100%',
                      maxHeight: 360,
                      objectFit: 'contain',
                      borderRadius: 8,
                      border: '1px solid var(--border-subtle)',
                    }}
                  />
                </div>
              )}

              {/* Preview images for Dual AI */}
              {mode === 'dual_ai' && (topPreviewUrl || sidePreviewUrl) && (
                <div style={{ marginTop: 16, display: 'grid', gridTemplateColumns: '1fr 1fr', gap: 16 }}>
                  {topPreviewUrl && (
                    <div>
                      <div style={{ fontSize: '0.9rem', color: 'var(--text-muted)', marginBottom: 8 }}>Top View Image</div>
                      <img
                        src={topPreviewUrl}
                        alt="Top View"
                        style={{
                          width: '100%',
                          maxHeight: 250,
                          objectFit: 'contain',
                          borderRadius: 8,
                          border: '1px solid var(--border-subtle)',
                        }}
                      />
                    </div>
                  )}
                  {sidePreviewUrl && (
                    <div>
                      <div style={{ fontSize: '0.9rem', color: 'var(--text-muted)', marginBottom: 8 }}>Side View Image</div>
                      <img
                        src={sidePreviewUrl}
                        alt="Side View"
                        style={{
                          width: '100%',
                          maxHeight: 250,
                          objectFit: 'contain',
                          borderRadius: 8,
                          border: '1px solid var(--border-subtle)',
                        }}
                      />
                    </div>
                  )}
                </div>
              )}
            </div>
          )}

          {/* ─── YOLO result (unchanged display) ─────────────────────── */}
          {yoloResult && (
            <div>
              {yoloResult.tray_count > 0 && yoloResult.confidence < 0.5 && (
                <div
                  style={{
                    display: 'flex',
                    alignItems: 'center',
                    gap: 8,
                    padding: '12px',
                    backgroundColor: 'rgba(245, 158, 11, 0.1)',
                    color: 'var(--warning-600)',
                    borderRadius: 6,
                    marginBottom: 16,
                    fontSize: '0.9rem',
                  }}
                >
                  <AlertTriangle size={20} />
                  <span>{t('eggCounter.yoloWarning')}</span>
                </div>
              )}

              <div style={{ display: 'grid', gridTemplateColumns: '1fr', gap: 16, marginBottom: 24 }}>
                <div
                  style={{
                    backgroundColor: target === 'hens' ? 'rgba(239, 68, 68, 0.1)' : (target === 'eggs' ? 'rgba(245, 158, 11, 0.1)' : 'rgba(59, 130, 246, 0.1)'),
                    padding: '16px',
                    borderRadius: 8,
                    textAlign: 'center',
                  }}
                >
                  <div
                    style={{
                      color: target === 'hens' ? 'var(--danger-500)' : (target === 'eggs' ? '#f59e0b' : 'var(--brand-600)'),
                      fontSize: '0.85rem',
                      textTransform: 'uppercase',
                      letterSpacing: '0.5px',
                      marginBottom: 4,
                      fontWeight: 600,
                    }}
                  >
                    {target === 'hens' ? t('eggCounter.totalHens') : (target === 'eggs' ? t('eggCounter.totalEggs') : t('eggCounter.totalTrays'))}
                  </div>
                  <div style={{ fontSize: '3rem', fontWeight: 'bold', color: 'var(--text-primary)' }}>
                    {target === 'hens' ? (yoloResult.hen_count ?? 0) : (target === 'eggs' ? (yoloResult.egg_count ?? 0) : (yoloResult.tray_count ?? 0))}
                  </div>
                  {target === 'trays' && yoloResult.egg_count !== undefined && yoloResult.egg_count > 0 && (
                    <div style={{ marginTop: 12, display: 'flex', flexDirection: 'column', gap: '8px', alignItems: 'center' }}>
                      <div style={{ fontSize: '1rem', color: 'var(--brand-700)', fontWeight: 600 }}>
                        {t('eggCounter.yoloCalculatedEggs', { count: yoloResult.egg_count })}
                      </div>
                      
                      {yoloResult.expected_egg_count !== undefined && yoloResult.expected_egg_count > yoloResult.egg_count && (
                        <div style={{ display: 'flex', gap: '16px', marginTop: '4px' }}>
                          <div style={{ fontSize: '0.9rem', color: 'var(--text-muted)' }}>
                            <span style={{ fontWeight: 500 }}>Expected:</span> {yoloResult.expected_egg_count}
                          </div>
                          <div style={{ fontSize: '0.9rem', color: 'var(--danger-600)', fontWeight: 600 }}>
                            <span style={{ fontWeight: 500 }}>Missing (Deducted):</span> {yoloResult.missing_egg_count}
                          </div>
                        </div>
                      )}
                    </div>
                  )}
                  {target !== 'hens' && yoloResult.egg_count !== undefined && yoloResult.egg_count > 0 && eggCost > 0 && (
                    <div style={{ fontSize: '1.2rem', color: '#10b981', marginTop: 12, fontWeight: 700, padding: '8px', backgroundColor: 'rgba(16, 185, 129, 0.1)', borderRadius: '6px', display: 'inline-block' }}>
                      Total Cost: ₹{(yoloResult.egg_count * eggCost).toFixed(2)}
                    </div>
                  )}
                  {yoloResult.tray_count !== undefined && (
                    <div style={{ fontSize: '0.85rem', color: 'var(--brand-700)', marginTop: 4 }}>
                      {t('eggCounter.yoloConfidence', { level: (yoloResult.confidence * 100).toFixed(1) })}
                    </div>
                  )}
                </div>
              </div>

              <div style={{ fontSize: '0.9rem', color: 'var(--text-muted)', marginBottom: 8 }}>
                {t('eggCounter.processedImage')}
              </div>
              <img
                src={`data:image/jpeg;base64,${yoloResult.result_image}`}
                alt="Processed Result"
                style={{
                  width: '100%',
                  maxHeight: 400,
                  objectFit: 'contain',
                  borderRadius: 8,
                  border: '1px solid var(--border-subtle)',
                }}
              />
            </div>
          )}
        </div>
      </div>
    </div>
  )
}

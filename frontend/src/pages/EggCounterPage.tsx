import React, { useState, useRef } from 'react'
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
} from 'lucide-react'

// ─── Types ────────────────────────────────────────────────────────────────────

interface YoloResult {
  success: boolean
  tray_count: number
  egg_count?: number
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
  const [isCameraOpen, setIsCameraOpen] = useState(false)
  const fileInputRef = useRef<HTMLInputElement>(null)
  const cameraInputRef = useRef<HTMLInputElement>(null)
  const videoRef = useRef<HTMLVideoElement>(null)
  const canvasRef = useRef<HTMLCanvasElement>(null)
  const streamRef = useRef<MediaStream | null>(null)

  const stopCamera = () => {
    if (streamRef.current) {
      streamRef.current.getTracks().forEach(track => track.stop())
      streamRef.current = null
    }
    setIsCameraOpen(false)
  }

  const startCamera = async () => {
    setOpenaiResult(null)
    setYoloResult(null)
    setError(null)
    setStatus(null)

    if (!navigator.mediaDevices || !navigator.mediaDevices.getUserMedia) {
      setError('Camera access is not supported in this browser. Ensure you are using HTTPS. Falling back to native camera.')
      cameraInputRef.current?.click()
      return
    }

    try {
      let stream;
      try {
        // Try environment (back) camera first for mobile
        stream = await navigator.mediaDevices.getUserMedia({ video: { facingMode: { ideal: 'environment' } } })
      } catch (err) {
        // Fallback to default camera (for desktop webcams)
        stream = await navigator.mediaDevices.getUserMedia({ video: true })
      }
      streamRef.current = stream
      setIsCameraOpen(true)
      // We need to wait a tick for the video element to render before attaching the stream
      setTimeout(() => {
        if (videoRef.current) {
          videoRef.current.srcObject = stream
          videoRef.current.play()
        }
      }, 100)
    } catch (err: any) {
      console.error('Camera access denied:', err)
      setError('Camera access denied or no camera found. Please allow permissions in your browser.')
    }
  }

  const capturePhoto = () => {
    if (videoRef.current && canvasRef.current) {
      const video = videoRef.current
      const canvas = canvasRef.current
      canvas.width = video.videoWidth
      canvas.height = video.videoHeight
      const ctx = canvas.getContext('2d')
      if (ctx) {
        ctx.drawImage(video, 0, 0, canvas.width, canvas.height)
        canvas.toBlob((blob) => {
          if (blob) {
            const file = new File([blob], `camera_capture_${Date.now()}.jpg`, { type: 'image/jpeg' })
            if (activeUploadContext === 'top') {
              setTopFile(file)
              setTopPreviewUrl(URL.createObjectURL(file))
            } else if (activeUploadContext === 'side') {
              setSideFile(file)
              setSidePreviewUrl(URL.createObjectURL(file))
            } else {
              setSelectedFile(file)
              setPreviewUrl(URL.createObjectURL(file))
            }
            stopCamera()
          }
        }, 'image/jpeg', 0.9)
      }
    }
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

          {/* ─── Camera / Upload UI ──────────────────────────────────────────── */}
          {isCameraOpen ? (
            <div style={{ marginBottom: 24 }}>
              <div style={{ position: 'relative', width: '100%', borderRadius: 8, overflow: 'hidden', backgroundColor: '#000', marginBottom: 12 }}>
                <video
                  ref={videoRef}
                  style={{ width: '100%', display: 'block' }}
                  playsInline
                  autoPlay
                  muted
                />
              </div>
              <canvas ref={canvasRef} style={{ display: 'none' }} />
              <div style={{ display: 'flex', gap: 12 }}>
                <button
                  className="btn btn-primary"
                  onClick={capturePhoto}
                  style={{ flex: 1, display: 'flex', alignItems: 'center', justifyContent: 'center', gap: 8 }}
                >
                  <Camera size={18} /> Take Photo
                </button>
                <button
                  className="btn btn-secondary"
                  onClick={stopCamera}
                  style={{ flex: 1, display: 'flex', alignItems: 'center', justifyContent: 'center', gap: 8 }}
                >
                  <X size={18} /> Cancel
                </button>
              </div>
            </div>
          ) : (
            <>
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

              {/* Camera capture button opens custom camera */}
              <button
                className="btn btn-secondary"
                onClick={() => {
                  if (mode === 'dual_ai') {
                    setActiveUploadContext(topFile ? 'side' : 'top');
                  } else {
                    setActiveUploadContext('single');
                  }
                  startCamera();
                }}
                style={{ width: '100%', marginBottom: 24, display: 'flex', alignItems: 'center', justifyContent: 'center', gap: 6 }}
              >
                <Camera size={16} /> {t('eggCounter.captureCamera')} {mode === 'dual_ai' ? (topFile ? '(Side View)' : '(Top View)') : ''}
              </button>
            </>
          )}

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
                     <div style={{ fontSize: '0.8rem', color: 'var(--brand-700)', marginTop: 8 }}>
                       {t('eggCounter.calculatedTrays', { count: openaiResult.tray_count })}
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
                    {openaiResult.hen_count}
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
                    {target === 'hens' ? yoloResult.hen_count : (target === 'eggs' ? yoloResult.egg_count : yoloResult.tray_count)}
                  </div>
                  {target === 'trays' && yoloResult.egg_count !== undefined && yoloResult.egg_count > 0 && (
                    <div style={{ fontSize: '1rem', color: 'var(--brand-700)', marginTop: 8, fontWeight: 600 }}>
                      {t('eggCounter.yoloCalculatedEggs', { count: yoloResult.egg_count })}
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

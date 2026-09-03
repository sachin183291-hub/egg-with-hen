import { useState } from 'react'
import { Thermometer, UploadCloud, Activity, Camera, RefreshCw, Video } from 'lucide-react'
import { aiApi } from '../services/api'

export default function ThermalCameraPage() {
  const [selectedImage, setSelectedImage] = useState<File | null>(null)
  const [previewUrl, setPreviewUrl] = useState<string | null>(null)
  const [isVideo, setIsVideo] = useState(false)
  
  const [isAnalyzing, setIsAnalyzing] = useState(false)
  const [result, setResult] = useState<any>(null)
  const [error, setError] = useState<string | null>(null)
  
  const [processedVideoUrl, setProcessedVideoUrl] = useState<string | null>(null)

  const handleImageUpload = (e: React.ChangeEvent<HTMLInputElement>) => {
    const file = e.target.files?.[0]
    if (file) {
      const isVid = file.type.includes('video') || file.name.match(/\.(mp4|avi|mov|webm)$/i) !== null
      setIsVideo(isVid)
      setSelectedImage(file)
      setPreviewUrl(URL.createObjectURL(file))
      setResult(null)
      setProcessedVideoUrl(null)
      setError(null)
    }
  }

  const startAnalysis = async () => {
    if (!selectedImage) return
    setIsAnalyzing(true)
    setError(null)
    
    try {
      const formData = new FormData()
      formData.append('image', selectedImage)
      formData.append('min_temp', '20.0')
      formData.append('max_temp', '40.0')

      if (isVideo) {
        const response = await aiApi.thermalAnalyzeVideo(formData)
        // Response is a blob
        const videoBlob = new Blob([response.data], { type: 'video/mp4' })
        const url = URL.createObjectURL(videoBlob)
        setProcessedVideoUrl(url)
        
        // Try to get count from headers
        const countHeader = response.headers['x-hen-count']
        setResult({ hen_count: countHeader ? parseInt(countHeader, 10) : 0, is_video: true })
      } else {
        const response = await aiApi.thermalAnalyze(formData)
        setResult(response.data)
      }
    } catch (err: any) {
      if (err.response?.data instanceof Blob) {
        const text = await err.response.data.text()
        try {
          const json = JSON.parse(text)
          setError(json.detail || 'Failed to process thermal video.')
        } catch {
          setError('Failed to process thermal video.')
        }
      } else {
        setError(err.response?.data?.detail || 'Failed to process thermal media.')
      }
    } finally {
      setIsAnalyzing(false)
    }
  }

  const reset = () => {
    setSelectedImage(null)
    setPreviewUrl(null)
    setIsVideo(false)
    setResult(null)
    setProcessedVideoUrl(null)
    setError(null)
    setIsAnalyzing(false)
  }

  return (
    <div className="page-container page-with-bg" style={{ backgroundImage: "linear-gradient(rgba(255, 255, 255, 0.65), rgba(255, 255, 255, 0.65)), url('/thermal-bg.jpg')", backgroundSize: "cover", backgroundPosition: "center" }}>
      <header className="page-header" style={{ marginBottom: '32px' }}>
        <div style={{ display: 'flex', alignItems: 'center', gap: 12 }}>
          <div className="page-icon-wrapper" style={{ background: '#ef4444' }}>
            <Thermometer size={20} color="white" />
          </div>
          <div>
            <h1 className="page-title">
              Thermal Drone Camera
            </h1>
            <p className="page-subtitle">
              Upload a drone video or image to simulate thermal view and detect hens based on heat hotspots (20°C - 40°C).
            </p>
          </div>
        </div>
      </header>

      <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: '24px' }}>
        {/* Upload & Preview Section */}
        <div className="card" style={{ padding: '24px', display: 'flex', flexDirection: 'column', gap: '20px' }}>
          <h3 style={{ fontSize: '1.25rem', fontWeight: '600', display: 'flex', alignItems: 'center', gap: '8px' }}>
            <Camera size={20} className="text-brand" /> Original View
          </h3>
          
          {!previewUrl ? (
            <label style={{
              display: 'flex', flexDirection: 'column', alignItems: 'center', justifyContent: 'center',
              border: '2px dashed var(--border)', borderRadius: '12px', padding: '48px', cursor: 'pointer',
              background: 'rgba(255,255,255,0.02)', transition: 'all 0.2s ease'
            }}>
              <UploadCloud size={48} color="var(--brand-400)" style={{ marginBottom: '16px' }} />
              <span style={{ fontSize: '1.1rem', fontWeight: '500', marginBottom: '8px' }}>Click to upload video or image</span>
              <span style={{ fontSize: '0.9rem', color: 'var(--text-muted)' }}>MP4, AVI, PNG, JPG</span>
              <input type="file" accept="image/*,video/*" onChange={handleImageUpload} style={{ display: 'none' }} />
            </label>
          ) : (
            <div style={{ position: 'relative', borderRadius: '12px', overflow: 'hidden', border: '1px solid var(--border)' }}>
              {isVideo ? (
                <video src={previewUrl} controls style={{ width: '100%', height: 'auto', maxHeight: '400px', objectFit: 'cover' }} />
              ) : (
                <img src={previewUrl} alt="Selected view" style={{ width: '100%', height: 'auto', maxHeight: '400px', objectFit: 'cover' }} />
              )}
              <button 
                onClick={reset}
                style={{
                  position: 'absolute', top: '12px', right: '12px', background: 'rgba(0,0,0,0.6)', 
                  border: 'none', color: '#fff', borderRadius: '50%', width: '36px', height: '36px',
                  display: 'flex', alignItems: 'center', justifyContent: 'center', cursor: 'pointer', backdropFilter: 'blur(4px)'
                }}
              >
                <RefreshCw size={18} />
              </button>
            </div>
          )}

          {error && (
            <div style={{ padding: '12px', background: 'rgba(239, 68, 68, 0.1)', color: '#ef4444', borderRadius: '8px' }}>
              {error}
            </div>
          )}

          {previewUrl && !result && (
            <button 
              onClick={startAnalysis} 
              disabled={isAnalyzing}
              className="btn btn-primary"
              style={{ width: '100%', padding: '14px', fontSize: '1.1rem', display: 'flex', justifyContent: 'center', gap: '10px' }}
            >
              {isAnalyzing ? (
                <>
                  <div className="spinner" style={{ width: '20px', height: '20px', borderTopColor: 'white' }}></div>
                  Applying Thermal Filter & Counting...
                </>
              ) : (
                <>
                  <Activity size={20} />
                  Analyze Temperature Hotspots
                </>
              )}
            </button>
          )}
        </div>

        {/* Results Section */}
        <div className="card" style={{ padding: '24px', position: 'relative', overflow: 'hidden' }}>
          <h3 style={{ fontSize: '1.25rem', fontWeight: '600', display: 'flex', alignItems: 'center', gap: '8px', marginBottom: '24px' }}>
            <Thermometer size={20} className="text-brand" /> Thermal Analysis Result
          </h3>

          {!result && !isAnalyzing && (
            <div style={{ display: 'flex', flexDirection: 'column', alignItems: 'center', justifyContent: 'center', height: '80%', opacity: 0.5 }}>
              <Thermometer size={64} color="var(--text-muted)" style={{ marginBottom: '16px' }} />
              <p>Upload media to see the thermal detection.</p>
            </div>
          )}

          {isAnalyzing && (
            <div style={{ display: 'flex', flexDirection: 'column', alignItems: 'center', justifyContent: 'center', height: '80%' }}>
              <div className="pulse-ring" style={{ width: '80px', height: '80px', background: '#ef4444', borderRadius: '50%', marginBottom: '24px', animation: 'pulse-red 1.5s infinite' }}></div>
              <p style={{ fontSize: '1.1rem', color: '#ef4444', fontWeight: '500' }}>Processing thermal mapping...</p>
              {isVideo && <p style={{ fontSize: '0.9rem', color: 'var(--text-muted)' }}>(Video processing may take a few moments)</p>}
            </div>
          )}

          {result && (
            <div className="fade-in">
              {/* Summary header */}
              <div style={{ display: 'flex', alignItems: 'center', gap: '24px', marginBottom: '20px', padding: '20px', background: 'rgba(239, 68, 68, 0.1)', borderRadius: '12px', border: '1px solid rgba(239,68,68,0.2)' }}>
                <div>
                  <div style={{ fontSize: '0.85rem', textTransform: 'uppercase', letterSpacing: '1px', color: '#ef4444', fontWeight: '700', marginBottom: '4px' }}>
                    {isVideo ? 'Peak Hens Detected' : 'Hens Detected (Thermal)'}
                  </div>
                  <div style={{ fontSize: '2.8rem', fontWeight: '800', color: '#ef4444', lineHeight: 1 }}>{result.hen_count}</div>
                  <div style={{ fontSize: '0.8rem', color: '#ef4444', marginTop: '4px' }}>Temperature filter: 20°C – 40°C</div>
                </div>
                <div style={{ flex: 1, textAlign: 'right', fontSize: '0.9rem', color: 'var(--text-muted)' }}>
                  {result.hen_count > 0 
                    ? `Avg: ${(result.hens?.reduce((a: number, h: any) => a + h.temperature, 0) / (result.hens?.length || 1)).toFixed(1)}°C`
                    : 'No hens detected in range'}
                </div>
              </div>

              {/* Per-hen temperature table */}
              {result.hens && result.hens.length > 0 && (
                <div style={{ marginBottom: '16px', borderRadius: '10px', overflow: 'hidden', border: '1px solid var(--border)' }}>
                  <table style={{ width: '100%', borderCollapse: 'collapse', fontSize: '0.9rem' }}>
                    <thead>
                      <tr style={{ background: 'var(--bg-elevated)' }}>
                        <th style={{ padding: '10px 14px', textAlign: 'left', color: 'var(--text-muted)', fontWeight: '600' }}>Hen #</th>
                        <th style={{ padding: '10px 14px', textAlign: 'center', color: 'var(--text-muted)', fontWeight: '600' }}>Temperature</th>
                        <th style={{ padding: '10px 14px', textAlign: 'center', color: 'var(--text-muted)', fontWeight: '600' }}>Status</th>
                      </tr>
                    </thead>
                    <tbody>
                      {result.hens.map((hen: any) => {
                        const norm = Math.min(1, Math.max(0, (hen.temperature - 20) / 20))
                        const r = Math.round(norm * 255)
                        const g = Math.round((1 - norm) * 180)
                        return (
                          <tr key={hen.hen_number} style={{ borderTop: '1px solid var(--border)', transition: 'background 0.15s' }}>
                            <td style={{ padding: '10px 14px', fontWeight: '700' }}>🐔 Hen {hen.hen_number}</td>
                            <td style={{ padding: '10px 14px', textAlign: 'center' }}>
                              <span style={{
                                display: 'inline-block', padding: '3px 12px', borderRadius: '20px',
                                background: `rgba(${r},${g},0,0.18)`,
                                color: `rgb(${r},${g},0)`,
                                fontWeight: '700', fontSize: '0.95rem'
                              }}>
                                {hen.temperature.toFixed(1)}°C
                              </span>
                            </td>
                            <td style={{ padding: '10px 14px', textAlign: 'center' }}>
                              <span style={{
                                display: 'inline-block', padding: '2px 10px', borderRadius: '12px',
                                background: hen.temperature >= 38 ? 'rgba(239,68,68,0.15)' : hen.temperature >= 34 ? 'rgba(251,146,60,0.15)' : 'rgba(34,197,94,0.15)',
                                color: hen.temperature >= 38 ? '#ef4444' : hen.temperature >= 34 ? '#fb923c' : '#22c55e',
                                fontSize: '0.8rem', fontWeight: '600'
                              }}>
                                {hen.temperature >= 38 ? '🔴 Hot' : hen.temperature >= 34 ? '🟠 Warm' : '🟢 Normal'}
                              </span>
                            </td>
                          </tr>
                        )
                      })}
                    </tbody>
                  </table>
                </div>
              )}

              {isVideo && processedVideoUrl && (
                 <div style={{ position: 'relative', borderRadius: '12px', overflow: 'hidden', border: '1px solid var(--border)', marginTop: '16px' }}>
                    <video src={processedVideoUrl} controls autoPlay loop style={{ width: '100%', height: 'auto', maxHeight: '400px', objectFit: 'cover' }} />
                 </div>
              )}

              {!isVideo && result.result_image && (
                <div style={{ position: 'relative', borderRadius: '12px', overflow: 'hidden', border: '1px solid var(--border)', marginTop: '16px' }}>
                  <img src={`data:image/jpeg;base64,${result.result_image}`} alt="Thermal Result" style={{ width: '100%', height: 'auto', maxHeight: '400px', objectFit: 'cover' }} />
                </div>
              )}
            </div>
          )}
        </div>
      </div>
      
      <style dangerouslySetInnerHTML={{__html: `
        @keyframes pulse-red {
          0% { transform: scale(0.95); box-shadow: 0 0 0 0 rgba(239, 68, 68, 0.7); }
          70% { transform: scale(1); box-shadow: 0 0 0 20px rgba(239, 68, 68, 0); }
          100% { transform: scale(0.95); box-shadow: 0 0 0 0 rgba(239, 68, 68, 0); }
        }
        .fade-in { animation: fadeIn 0.5s ease forwards; }
        @keyframes fadeIn { from { opacity: 0; transform: translateY(10px); } to { opacity: 1; transform: translateY(0); } }
      `}} />
    </div>
  )
}

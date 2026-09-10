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
  const [videoStreamUrl, setVideoStreamUrl] = useState<string | null>(null)
  const [videoJobId, setVideoJobId] = useState<string | null>(null)
  const [processingProgress, setProcessingProgress] = useState(0)
  const [mjpegStreamUrl, setMjpegStreamUrl] = useState<string | null>(null)

  // Live Stream State
  const [activeTab, setActiveTab] = useState<'upload' | 'live'>('upload')
  const [liveStreamIp, setLiveStreamIp] = useState<string | null>(null)
  const [isLiveConnected, setIsLiveConnected] = useState(false)
  const [finalRecord, setFinalRecord] = useState<{ count: number, videoUrl: string } | null>(null)
  const [isSaving, setIsSaving] = useState(false)
  const API_URL = import.meta.env.VITE_API_URL || ''

  // Poll for job completion
  const pollJobStatus = async (jobId: string) => {
    const interval = setInterval(async () => {
      try {
        const res = await fetch(`${API_URL}/api/ai/video-job-status/${jobId}`)
        const job = await res.json()
        setProcessingProgress(job.progress || 0)
        if (job.status === 'done') {
          clearInterval(interval)
          const videoUrl = `${API_URL}/api/ai/serve-video/${jobId}`
          setProcessedVideoUrl(videoUrl)
          setResult({ is_video: true, hen_count: job.hen_count })
          setIsAnalyzing(false)
        } else if (job.status === 'error') {
          clearInterval(interval)
          setError(`Processing failed: ${job.error}`)
          setIsAnalyzing(false)
        }
      } catch {
        // ignore poll errors, will retry
      }
    }, 2000)
  }


  const connectLiveStream = () => {
    const ip = localStorage.getItem('droneIP')
    if (ip) {
      setLiveStreamIp(ip)
      setIsLiveConnected(true)
      setFinalRecord(null)
      setError(null)
    } else {
      setError("No Drone IP found. Please configure it in the Drone Control menu first.")
    }
  }

  const handleStopStream = async () => {
    setIsLiveConnected(false)
    setIsSaving(true)
    try {
      await new Promise(res => setTimeout(res, 1000))
      const res = await fetch(`${API_URL}/api/ai/drone-stream/latest`)
      const data = await res.json()
      if (data.video_path) {
        setFinalRecord({ count: data.final_count, videoUrl: `${API_URL}/api/ai/drone-stream/video` })
      }
    } catch (e) {
      console.error("Error fetching latest record:", e)
    } finally {
      setIsSaving(false)
    }
  }

  const handleImageUpload = async (e: React.ChangeEvent<HTMLInputElement>) => {
    const file = e.target.files?.[0]
    if (file) {
      const isVid = file.type.includes('video') || file.name.match(/\.(mp4|avi|mov|webm)$/i) !== null
      setIsVideo(isVid)
      setSelectedImage(file)
      setPreviewUrl(URL.createObjectURL(file))
      setResult(null)
      setProcessedVideoUrl(null)
      setVideoStreamUrl(null)
      setVideoJobId(null)
      setMjpegStreamUrl(null)
      setError(null)
      
      if (isVid) {
         // Automatically start the instant MJPEG stream for videos
         setIsAnalyzing(true)
         const formData = new FormData()
         formData.append('file', file)
         try {
             const res = await fetch(`${API_URL}/api/ai/upload-temp-video`, { method: 'POST', body: formData })
             const data = await res.json()
             if (data.path) {
                 setMjpegStreamUrl(`${API_URL}/api/ai/stream-uploaded-video?path=${encodeURIComponent(data.path)}`)
                 setResult({ is_video: true, hen_count: "Counting..." }) // Fake result to hide the "Analyze" button
             }
         } catch(e) {
             setError("Failed to start automatic video stream.")
         } finally {
             setIsAnalyzing(false)
         }
      }
    }
  }

  const startAnalysis = async () => {
    if (!selectedImage) return
    setIsAnalyzing(true)
    setError(null)
    setVideoStreamUrl(null)
    setProcessedVideoUrl(null)
    setProcessingProgress(0)
    setVideoJobId(null)

    try {
      const formData = new FormData()
      formData.append('image', selectedImage)
      formData.append('min_temp', '20.0')
      formData.append('max_temp', '40.0')

      if (isVideo) {
        // Upload the video — backend starts background job and returns job_id instantly
        const response = await aiApi.thermalAnalyzeVideo(formData)
        const { job_id } = response.data
        setVideoJobId(job_id)
        // Start polling — setIsAnalyzing(false) happens inside pollJobStatus when done
        pollJobStatus(job_id)
        // Don't call setIsAnalyzing(false) here!
        return
      } else {
        const response = await aiApi.thermalAnalyze(formData)
        setResult(response.data)
      }
    } catch (err: any) {
      let errorMessage = 'Failed to process thermal media.'
      try {
        if (err.response?.data?.detail) {
          errorMessage = err.response.data.detail
        } else if (err.message) {
          errorMessage = err.message
        }
      } catch {
        // keep default errorMessage
      }
      setError(`Error: ${errorMessage}`)
    } finally {
      if (!isVideo) setIsAnalyzing(false)
    }
  }

  const reset = () => {
    setSelectedImage(null)
    setPreviewUrl(null)
    setIsVideo(false)
    setResult(null)
    setProcessedVideoUrl(null)
    setVideoStreamUrl(null)
    setVideoJobId(null)
    setMjpegStreamUrl(null)
    setProcessingProgress(0)
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
              Upload a drone video or stream live to simulate thermal view and detect hens based on heat hotspots (20°C - 40°C).
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

          <div style={{ display: 'flex', gap: '12px', marginBottom: '16px' }}>
            <button
              onClick={() => setActiveTab('upload')}
              className={`btn ${activeTab === 'upload' ? 'btn-primary' : 'btn-secondary'}`}
              style={{ flex: 1 }}
            >
              <UploadCloud size={18} style={{ marginRight: 8 }} /> Upload Media
            </button>
            <button
              onClick={() => setActiveTab('live')}
              className={`btn ${activeTab === 'live' ? 'btn-primary' : 'btn-secondary'}`}
              style={{ flex: 1 }}
            >
              <Video size={18} style={{ marginRight: 8 }} /> Live Drone Feed
            </button>
          </div>

          {activeTab === 'upload' && !previewUrl && (
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
          )}

          {activeTab === 'live' && !isLiveConnected && !finalRecord && (
            <div style={{
              display: 'flex', flexDirection: 'column', alignItems: 'center', justifyContent: 'center',
              border: '2px dashed var(--border)', borderRadius: '12px', padding: '48px',
              background: 'rgba(255,255,255,0.02)'
            }}>
              <Video size={48} color="var(--brand-400)" style={{ marginBottom: '16px' }} />
              <span style={{ fontSize: '1.1rem', fontWeight: '500', marginBottom: '16px' }}>Connect to Global Drone IP</span>
              <button className="btn btn-primary" onClick={connectLiveStream}>
                Connect Live Stream
              </button>
            </div>
          )}

          {activeTab === 'live' && isLiveConnected && liveStreamIp && (
            <div style={{ position: 'relative', borderRadius: '12px', overflow: 'hidden', border: '1px solid var(--border)' }}>
              <img
                src={`${API_URL}/api/ai/drone-stream?ip=${encodeURIComponent(liveStreamIp)}`}
                alt="Live Thermal Stream"
                style={{ width: '100%', height: 'auto', maxHeight: '400px', objectFit: 'cover' }}
              />
              <button
                onClick={handleStopStream}
                disabled={isSaving}
                className="btn btn-danger"
                style={{
                  position: 'absolute', bottom: '16px', left: '50%', transform: 'translateX(-50%)',
                  background: '#ef4444', color: 'white', border: 'none', padding: '8px 24px',
                  borderRadius: '24px', fontWeight: 'bold', boxShadow: '0 4px 12px rgba(239,68,68,0.4)',
                  cursor: 'pointer'
                }}
              >
                {isSaving ? 'Saving...' : 'Stop & Save Recording'}
              </button>
            </div>
          )}

          {activeTab === 'live' && finalRecord && (
            <div style={{ borderRadius: '12px', padding: '24px', background: 'rgba(0,0,0,0.4)', border: '1px solid var(--border)', textAlign: 'center' }}>
              <h2 style={{ color: '#ef4444', marginBottom: '8px' }}>Final Count: {finalRecord.count} Hens</h2>
              <p style={{ color: 'var(--text-muted)', marginBottom: '16px' }}>Stream recorded and analyzed successfully.</p>
              <video src={finalRecord.videoUrl} controls style={{ width: '100%', maxHeight: '300px', borderRadius: '8px' }}></video>
              <button className="btn btn-secondary" onClick={() => setFinalRecord(null)} style={{ marginTop: '16px' }}>
                Start New Session
              </button>
            </div>
          )}

          {activeTab === 'upload' && previewUrl && (
            <div style={{ position: 'relative', borderRadius: '12px', overflow: 'hidden', border: videoStreamUrl ? '2px solid #ef4444' : '1px solid var(--border)' }}>
              {mjpegStreamUrl ? (
                <img src={mjpegStreamUrl} alt="Live processing stream" style={{ width: '100%', height: 'auto', maxHeight: '400px', objectFit: 'cover' }} />
              ) : isVideo ? (
                <video
                  src={previewUrl}
                  controls
                  autoPlay={!!videoStreamUrl}  
                  loop
                  muted
                  style={{ width: '100%', height: 'auto', maxHeight: '400px', objectFit: 'cover' }}
                />
              ) : (
                <img src={previewUrl} alt="Selected view" style={{ width: '100%', height: 'auto', maxHeight: '400px', objectFit: 'cover' }} />
              )}
              {videoStreamUrl && (
                <div style={{
                  position: 'absolute', top: '10px', left: '10px',
                  background: 'rgba(0,0,0,0.7)', color: '#fff',
                  borderRadius: '6px', padding: '4px 10px', fontSize: '0.78rem', fontWeight: 600
                }}>
                  📹 Original
                </div>
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

          {activeTab === 'upload' && previewUrl && !result && (
            <button
              onClick={startAnalysis}
              disabled={isAnalyzing}
              className="btn btn-primary"
              style={{ width: '100%', padding: '14px', fontSize: '1.1rem', display: 'flex', justifyContent: 'center', gap: '10px' }}
            >
              {isAnalyzing ? (
                <>
                  <div className="spinner" style={{ width: '20px', height: '20px', borderTopColor: 'white' }}></div>
                  {isVideo ? 'Uploading video...' : 'Applying Thermal Filter & Counting...'}
                </>
              ) : (
                <>
                  <Activity size={20} />
                  {isVideo ? '🐔 Analyze & Count Hens Live' : 'Analyze Temperature Hotspots'}
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

          {!result && !isAnalyzing && activeTab === 'upload' && (
            <div style={{ display: 'flex', flexDirection: 'column', alignItems: 'center', justifyContent: 'center', height: '80%', opacity: 0.5 }}>
              <Thermometer size={64} color="var(--text-muted)" style={{ marginBottom: '16px' }} />
              <p>Upload media to see the thermal detection.</p>
            </div>
          )}

          {!result && !isAnalyzing && activeTab === 'live' && (
            <div style={{ display: 'flex', flexDirection: 'column', alignItems: 'center', justifyContent: 'center', height: '80%', opacity: 0.5 }}>
              <Activity size={64} color="var(--text-muted)" style={{ marginBottom: '16px' }} />
              <p>Live stream results will be shown here during tracking.</p>
            </div>
          )}

          {mjpegStreamUrl && (
            <div style={{ textAlign: 'center', padding: '40px 20px', display: 'flex', flexDirection: 'column', gap: '16px' }}>
              <Activity size={48} color="#ef4444" style={{ margin: '0 auto' }} />
              <h3 style={{ fontSize: '1.2rem', color: 'var(--text-muted)' }}>Counting automatically in real-time...</h3>
              <p style={{ color: 'var(--text-muted)' }}>See the video view on the left for the live count.</p>
            </div>
          )}

          {!mjpegStreamUrl && isAnalyzing && (
            <div style={{ display: 'flex', flexDirection: 'column', alignItems: 'center', justifyContent: 'center', height: '80%', gap: 16 }}>
              <div className="pulse-ring" style={{ width: '80px', height: '80px', background: '#ef4444', borderRadius: '50%', animation: 'pulse-red 1.5s infinite' }}></div>
              <p style={{ fontSize: '1.1rem', color: '#ef4444', fontWeight: '500' }}>
                {videoJobId ? `🐔 AI Processing... ${processingProgress}%` : (isVideo ? 'Uploading video...' : 'Processing...')}
              </p>
              {videoJobId && (
                <div style={{ width: '80%', background: 'rgba(239,68,68,0.15)', borderRadius: 8, height: 12, overflow: 'hidden' }}>
                  <div style={{
                    height: '100%', width: `${processingProgress}%`,
                    background: 'linear-gradient(90deg,#ef4444,#f97316)',
                    borderRadius: 8, transition: 'width 0.5s ease'
                  }} />
                </div>
              )}
              {videoJobId && <p style={{ fontSize: '0.85rem', color: 'var(--text-muted)' }}>Detecting hens with YOLOWorld AI — please wait...</p>}
            </div>
          )}

          {result && (
            <div className="fade-in">

              {/* Final processed video at normal speed */}
              {isVideo && processedVideoUrl && (
                <div style={{ marginBottom: '20px' }}>
                  <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', marginBottom: '10px' }}>
                    <span style={{ fontSize: '0.9rem', color: '#22c55e', fontWeight: '700' }}>✅ Processing Complete!</span>
                    <span style={{ fontSize: '1.1rem', color: '#ef4444', fontWeight: '800' }}>🐔 {result.hen_count} Hens Counted</span>
                  </div>
                  <div style={{ position: 'relative', borderRadius: '12px', overflow: 'hidden', border: '2px solid #22c55e' }}>
                    <video
                      src={processedVideoUrl}
                      controls
                      autoPlay
                      loop
                      style={{ width: '100%', height: 'auto', maxHeight: '420px', display: 'block', background: '#000' }}
                    />
                  </div>
                  <p style={{ fontSize: '0.8rem', color: 'var(--text-muted)', marginTop: '8px' }}>
                    Video plays at normal speed. Green boxes = detected hens. Count shown in top-left corner.
                  </p>
                </div>
              )}

              {/* Image result stats */}
              {!isVideo && (
                <div style={{ display: 'flex', alignItems: 'center', gap: '24px', marginBottom: '20px', padding: '20px', background: 'rgba(239, 68, 68, 0.1)', borderRadius: '12px', border: '1px solid rgba(239,68,68,0.2)' }}>
                  <div>
                    <div style={{ fontSize: '0.85rem', textTransform: 'uppercase', letterSpacing: '1px', color: '#ef4444', fontWeight: '700', marginBottom: '4px' }}>Hens Detected (Thermal)</div>
                    <div style={{ fontSize: '2.8rem', fontWeight: '800', color: '#ef4444', lineHeight: 1 }}>{result.hen_count}</div>
                    <div style={{ fontSize: '0.8rem', color: '#ef4444', marginTop: '4px' }}>Temperature filter: 20°C – 40°C</div>
                  </div>
                  <div style={{ flex: 1, textAlign: 'right', fontSize: '0.9rem', color: 'var(--text-muted)' }}>
                    {result.hen_count > 0
                      ? `Avg: ${(result.hens?.reduce((a: number, h: any) => a + h.temperature, 0) / (result.hens?.length || 1)).toFixed(1)}°C`
                      : 'No hens detected in range'}
                  </div>
                </div>
              )}

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

              {!isVideo && result.result_image && (
                <div style={{ position: 'relative', borderRadius: '12px', overflow: 'hidden', border: '1px solid var(--border)', marginTop: '16px' }}>
                  <img src={`data:image/jpeg;base64,${result.result_image}`} alt="Thermal Result" style={{ width: '100%', height: 'auto', maxHeight: '400px', objectFit: 'cover' }} />
                </div>
              )}
            </div>
          )}
        </div>
      </div>

      <style dangerouslySetInnerHTML={{
        __html: `
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

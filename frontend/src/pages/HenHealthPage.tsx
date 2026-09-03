import { useState } from 'react'
import { HeartPulse, UploadCloud, AlertCircle, CheckCircle, Activity, Camera, Leaf, RefreshCw } from 'lucide-react'

export default function HenHealthPage() {
  const [selectedImage, setSelectedImage] = useState<string | null>(null)
  const [isAnalyzing, setIsAnalyzing] = useState(false)
  const [result, setResult] = useState<any>(null)

  const handleImageUpload = (e: React.ChangeEvent<HTMLInputElement>) => {
    const file = e.target.files?.[0]
    if (file) {
      const imageUrl = URL.createObjectURL(file)
      setSelectedImage(imageUrl)
      setResult(null)
    }
  }

  const startAnalysis = () => {
    if (!selectedImage) return
    setIsAnalyzing(true)
    
    // Simulate AI analysis delay
    setTimeout(() => {
      setIsAnalyzing(false)
      setResult({
        overallHealth: 'Good',
        score: 92,
        metrics: [
          { name: 'Feather Condition', status: 'Excellent', score: 95 },
          { name: 'Comb Color', status: 'Normal', score: 90 },
          { name: 'Eye Clarity', status: 'Clear', score: 98 },
          { name: 'Posture/Activity', status: 'Active', score: 88 }
        ],
        recommendations: [
          'Maintain current feeding schedule.',
          'Ensure continuous access to fresh water.',
          'Monitor flock for next 7 days as standard procedure.'
        ]
      })
    }, 2500)
  }

  const reset = () => {
    setSelectedImage(null)
    setResult(null)
    setIsAnalyzing(false)
  }

  return (
    <div className="page-container" style={{ padding: '24px', maxWidth: '1200px', margin: '0 auto' }}>
      <div className="page-header" style={{ marginBottom: '32px' }}>
        <div>
          <h1 className="page-title" style={{ display: 'flex', alignItems: 'center', gap: '12px', fontSize: '2rem' }}>
            <HeartPulse color="#ef4444" size={32} />
            Hen Health AI Detection
          </h1>
          <p className="page-subtitle" style={{ fontSize: '1rem', color: 'var(--text-muted)' }}>
            Upload a photo of your poultry for instant AI-powered health diagnostics.
          </p>
        </div>
      </div>

      <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: '24px' }}>
        {/* Upload & Preview Section */}
        <div className="card" style={{ padding: '24px', display: 'flex', flexDirection: 'column', gap: '20px' }}>
          <h3 style={{ fontSize: '1.25rem', fontWeight: '600', display: 'flex', alignItems: 'center', gap: '8px' }}>
            <Camera size={20} className="text-brand" /> Image Capture
          </h3>
          
          {!selectedImage ? (
            <label style={{
              display: 'flex', flexDirection: 'column', alignItems: 'center', justifyContent: 'center',
              border: '2px dashed var(--border)', borderRadius: '12px', padding: '48px', cursor: 'pointer',
              background: 'rgba(255,255,255,0.02)', transition: 'all 0.2s ease'
            }}>
              <UploadCloud size={48} color="var(--brand-400)" style={{ marginBottom: '16px' }} />
              <span style={{ fontSize: '1.1rem', fontWeight: '500', marginBottom: '8px' }}>Click to upload hen photo</span>
              <span style={{ fontSize: '0.9rem', color: 'var(--text-muted)' }}>PNG, JPG, JPEG up to 5MB</span>
              <input type="file" accept="image/*" onChange={handleImageUpload} style={{ display: 'none' }} />
            </label>
          ) : (
            <div style={{ position: 'relative', borderRadius: '12px', overflow: 'hidden', border: '1px solid var(--border)' }}>
              <img src={selectedImage} alt="Selected hen" style={{ width: '100%', height: 'auto', maxHeight: '400px', objectFit: 'cover' }} />
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

          {selectedImage && !result && (
            <button 
              onClick={startAnalysis} 
              disabled={isAnalyzing}
              className="btn btn-primary"
              style={{ width: '100%', padding: '14px', fontSize: '1.1rem', display: 'flex', justifyContent: 'center', gap: '10px' }}
            >
              {isAnalyzing ? (
                <>
                  <div className="spinner" style={{ width: '20px', height: '20px', borderTopColor: 'white' }}></div>
                  Analyzing Vision Data...
                </>
              ) : (
                <>
                  <Activity size={20} />
                  Run AI Health Diagnostic
                </>
              )}
            </button>
          )}
        </div>

        {/* Results Section */}
        <div className="card" style={{ padding: '24px', position: 'relative', overflow: 'hidden' }}>
          <h3 style={{ fontSize: '1.25rem', fontWeight: '600', display: 'flex', alignItems: 'center', gap: '8px', marginBottom: '24px' }}>
            <Activity size={20} className="text-brand" /> Diagnostic Report
          </h3>

          {!result && !isAnalyzing && (
            <div style={{ display: 'flex', flexDirection: 'column', alignItems: 'center', justifyContent: 'center', height: '80%', opacity: 0.5 }}>
              <HeartPulse size={64} color="var(--text-muted)" style={{ marginBottom: '16px' }} />
              <p>Upload an image to see the diagnostic report.</p>
            </div>
          )}

          {isAnalyzing && (
            <div style={{ display: 'flex', flexDirection: 'column', alignItems: 'center', justifyContent: 'center', height: '80%' }}>
              <div className="pulse-ring" style={{ width: '80px', height: '80px', background: 'var(--brand-500)', borderRadius: '50%', marginBottom: '24px', animation: 'pulse 1.5s infinite' }}></div>
              <p style={{ fontSize: '1.1rem', color: 'var(--brand-400)', fontWeight: '500' }}>Processing neural network model...</p>
            </div>
          )}

          {result && (
            <div className="fade-in">
              <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', marginBottom: '32px', padding: '24px', background: 'rgba(16, 185, 129, 0.1)', borderRadius: '12px', border: '1px solid rgba(16,185,129,0.2)' }}>
                <div>
                  <div style={{ fontSize: '0.9rem', textTransform: 'uppercase', letterSpacing: '1px', color: '#10b981', fontWeight: '700', marginBottom: '4px' }}>Overall Health</div>
                  <div style={{ fontSize: '2.5rem', fontWeight: '800', color: '#10b981' }}>{result.overallHealth}</div>
                </div>
                <div style={{ width: '80px', height: '80px', borderRadius: '50%', border: '4px solid #10b981', display: 'flex', alignItems: 'center', justifyContent: 'center', fontSize: '1.5rem', fontWeight: '700', color: '#10b981' }}>
                  {result.score}%
                </div>
              </div>

              <div style={{ marginBottom: '24px' }}>
                <h4 style={{ fontSize: '1.1rem', marginBottom: '16px', color: 'var(--text-muted)' }}>Key Metrics</h4>
                <div style={{ display: 'flex', flexDirection: 'column', gap: '12px' }}>
                  {result.metrics.map((m: any, i: number) => (
                    <div key={i} style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', padding: '12px 16px', background: 'rgba(255,255,255,0.03)', borderRadius: '8px' }}>
                      <span style={{ fontWeight: '500' }}>{m.name}</span>
                      <div style={{ display: 'flex', alignItems: 'center', gap: '12px' }}>
                        <span style={{ color: m.score > 90 ? '#10b981' : '#f59e0b', fontSize: '0.9rem', fontWeight: '600' }}>{m.status}</span>
                        <div style={{ width: '100px', height: '6px', background: 'var(--border)', borderRadius: '3px', overflow: 'hidden' }}>
                          <div style={{ width: `${m.score}%`, height: '100%', background: m.score > 90 ? '#10b981' : '#f59e0b' }}></div>
                        </div>
                      </div>
                    </div>
                  ))}
                </div>
              </div>

              <div>
                <h4 style={{ fontSize: '1.1rem', marginBottom: '16px', color: 'var(--text-muted)', display: 'flex', alignItems: 'center', gap: '8px' }}>
                  <Leaf size={16} /> AI Recommendations
                </h4>
                <ul style={{ listStyle: 'none', padding: 0, margin: 0, display: 'flex', flexDirection: 'column', gap: '10px' }}>
                  {result.recommendations.map((rec: string, i: number) => (
                    <li key={i} style={{ display: 'flex', alignItems: 'flex-start', gap: '10px', fontSize: '0.95rem' }}>
                      <CheckCircle size={16} color="#10b981" style={{ marginTop: '2px', flexShrink: 0 }} />
                      <span style={{ color: 'var(--text-primary)' }}>{rec}</span>
                    </li>
                  ))}
                </ul>
              </div>
            </div>
          )}
        </div>
      </div>
      
      <style dangerouslySetInnerHTML={{__html: `
        @keyframes pulse {
          0% { transform: scale(0.95); box-shadow: 0 0 0 0 rgba(99, 102, 241, 0.7); }
          70% { transform: scale(1); box-shadow: 0 0 0 20px rgba(99, 102, 241, 0); }
          100% { transform: scale(0.95); box-shadow: 0 0 0 0 rgba(99, 102, 241, 0); }
        }
        .fade-in { animation: fadeIn 0.5s ease forwards; }
        @keyframes fadeIn { from { opacity: 0; transform: translateY(10px); } to { opacity: 1; transform: translateY(0); } }
      `}} />
    </div>
  )
}

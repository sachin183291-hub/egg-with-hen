import React, { useState } from 'react';
import { ImageUpload } from './components/ImageUpload';
import { DetectionResult } from './components/DetectionResult';
import { DetectionTable, type Detection } from './components/DetectionTable';
import { ControlPanel } from './components/ControlPanel';

const API_URL = 'http://localhost:8000/api';

function App() {
  const [isProcessing, setIsProcessing] = useState(false);
  const [confidenceThreshold, setConfidenceThreshold] = useState(0.50);
  const [error, setError] = useState<string | null>(null);
  
  // Results
  const [totalEggs, setTotalEggs] = useState<number | null>(null);
  const [averageConfidence, setAverageConfidence] = useState<number>(0);
  const [detections, setDetections] = useState<Detection[]>([]);
  const [annotatedImageUrl, setAnnotatedImageUrl] = useState<string | null>(null);

  const handleImageSelect = async (file: File) => {
    setIsProcessing(true);
    setError(null);
    
    const formData = new FormData();
    formData.append('image', file);
    formData.append('confidence_threshold', confidenceThreshold.toString());
    
    try {
      const response = await fetch(`${API_URL}/detect-eggs`, {
        method: 'POST',
        body: formData,
      });
      
      if (!response.ok) {
        const errorData = await response.json().catch(() => ({}));
        throw new Error(errorData.detail || 'Failed to process image. Make sure the backend is running.');
      }
      
      const data = await response.json();
      
      if (data.total_eggs === 0 || data.tray_count === 0) {
        setError("No objects detected in the uploaded image. Try adjusting the confidence threshold.");
      }
      
      setTotalEggs(data.total_eggs !== undefined ? data.total_eggs : data.tray_count);
      setAverageConfidence(data.average_confidence !== undefined ? data.average_confidence : data.confidence);
      
      const formattedDetections = (data.detections || []).map((det: any) => ({
        id: det.id,
        class: det.class,
        confidence: det.confidence,
        bbox: Array.isArray(det.bbox) ? {
          x: det.bbox[0],
          y: det.bbox[1],
          width: det.bbox[2] - det.bbox[0],
          height: det.bbox[3] - det.bbox[1]
        } : det.bbox
      }));
      setDetections(formattedDetections);
      
      if (data.result_image) {
        setAnnotatedImageUrl(`data:image/jpeg;base64,${data.result_image}`);
      } else {
        setAnnotatedImageUrl(`http://localhost:8000${data.annotated_image_url}`);
      }
      
    } catch (err: any) {
      console.error(err);
      setError(err.message || 'An unexpected error occurred.');
    } finally {
      setIsProcessing(false);
    }
  };

  const handleReset = () => {
    setTotalEggs(null);
    setAverageConfidence(0);
    setDetections([]);
    setAnnotatedImageUrl(null);
    setError(null);
  };

  return (
    <div className="min-h-screen bg-background font-sans selection:bg-primary/20 text-foreground">
      <header className="border-b border-border bg-card shadow-sm sticky top-0 z-10">
        <div className="max-w-7xl mx-auto px-4 sm:px-6 lg:px-8 h-16 flex items-center justify-between">
          <div className="flex items-center gap-3">
            <div className="w-8 h-8 rounded-lg bg-primary flex items-center justify-center text-primary-foreground font-bold shadow-sm">
              AI
            </div>
            <h1 className="text-xl font-bold tracking-tight">Egg Detection & Counting System</h1>
          </div>
          <div className="text-sm font-medium text-muted-foreground">
            Version 1.0.0
          </div>
        </div>
      </header>

      <main className="max-w-7xl mx-auto px-4 sm:px-6 lg:px-8 py-12">
        <div className="text-center mb-12">
          <h2 className="text-4xl font-extrabold tracking-tight mb-4">
            Automated Egg Detection
          </h2>
          <p className="text-lg text-muted-foreground max-w-2xl mx-auto">
            Upload an image to automatically detect and count eggs. Our computer vision model identifies individual eggs even in overlapping scenarios.
          </p>
        </div>

        {error && (
          <div className="max-w-2xl mx-auto mb-6 p-4 bg-destructive/10 text-destructive border border-destructive/20 rounded-lg shadow-sm animate-slide-up-fade">
            <p className="font-medium flex items-center gap-2">
              <span className="w-5 h-5 rounded-full bg-destructive/20 flex items-center justify-center font-bold">!</span>
              {error}
            </p>
          </div>
        )}

        {totalEggs === null && !annotatedImageUrl ? (
          <>
            <ImageUpload 
              onImageSelect={handleImageSelect} 
              isLoading={isProcessing} 
            />
            <ControlPanel 
              confidenceThreshold={confidenceThreshold} 
              setConfidenceThreshold={setConfidenceThreshold}
              disabled={isProcessing}
            />
          </>
        ) : (
          <>
            <DetectionResult 
              totalEggs={totalEggs || 0}
              averageConfidence={averageConfidence}
              annotatedImageUrl={annotatedImageUrl!}
              onReset={handleReset}
            />
            <DetectionTable detections={detections} />
          </>
        )}
      </main>
    </div>
  );
}

export default App;

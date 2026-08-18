import React from 'react';
import { Download, RefreshCcw } from 'lucide-react';

interface DetectionResultProps {
  totalEggs: number;
  averageConfidence: number;
  annotatedImageUrl: string;
  onReset: () => void;
}

export function DetectionResult({ totalEggs, averageConfidence, annotatedImageUrl, onReset }: DetectionResultProps) {
  
  const handleDownload = async () => {
    try {
      const response = await fetch(annotatedImageUrl);
      const blob = await response.blob();
      const url = window.URL.createObjectURL(blob);
      const a = document.createElement('a');
      a.style.display = 'none';
      a.href = url;
      a.download = 'egg-detection-result.jpg';
      document.body.appendChild(a);
      a.click();
      window.URL.revokeObjectURL(url);
    } catch (err) {
      console.error("Failed to download image", err);
    }
  };

  return (
    <div className="w-full max-w-4xl mx-auto mt-8 animate-slide-up-fade">
      <div className="text-center mb-8">
        <h2 className="text-3xl font-bold mb-2">EGG DETECTION RESULT</h2>
        <div className="inline-flex items-center gap-2 px-3 py-1 rounded-full bg-green-500/10 text-green-600 font-medium text-sm border border-green-500/20">
          <span className="w-2 h-2 rounded-full bg-green-500 animate-pulse" />
          Detection Status: Completed
        </div>
      </div>

      <div className="grid grid-cols-1 md:grid-cols-3 gap-6 mb-8">
        <div className="col-span-1 md:col-span-2 bg-card rounded-xl border border-border shadow-sm overflow-hidden flex flex-col">
          <div className="p-4 border-b border-border bg-muted/30">
            <h3 className="font-semibold">Annotated Image</h3>
          </div>
          <div className="flex-1 bg-black/5 p-4 flex items-center justify-center min-h-[300px]">
             <img 
              src={annotatedImageUrl} 
              alt="Detected Eggs" 
              className="max-h-[500px] object-contain rounded-lg shadow-sm"
            />
          </div>
        </div>

        <div className="space-y-6">
          <div className="bg-primary text-primary-foreground rounded-xl p-6 shadow-md relative overflow-hidden group">
            <div className="absolute top-0 right-0 p-4 opacity-10 group-hover:scale-110 transition-transform">
              <svg width="100" height="100" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2"><circle cx="12" cy="12" r="10"></circle></svg>
            </div>
            <p className="text-primary-foreground/80 font-medium text-sm mb-1 uppercase tracking-wider">Total Eggs Detected</p>
            <h3 className="text-6xl font-bold">{totalEggs}</h3>
          </div>
          
          <div className="bg-card rounded-xl p-6 border border-border shadow-sm">
            <p className="text-muted-foreground font-medium text-sm mb-1">Average Confidence</p>
            <h3 className="text-3xl font-bold">{(averageConfidence * 100).toFixed(1)}%</h3>
            <div className="w-full bg-muted rounded-full h-2 mt-4">
              <div 
                className="bg-green-500 h-2 rounded-full transition-all duration-1000" 
                style={{ width: `${averageConfidence * 100}%` }} 
              />
            </div>
          </div>

          <div className="flex flex-col gap-3">
            <button 
              onClick={handleDownload}
              className="w-full py-3 px-4 bg-secondary hover:bg-secondary/80 text-secondary-foreground rounded-lg font-medium flex items-center justify-center gap-2 transition-colors border border-border"
            >
              <Download className="w-5 h-5" />
              Download Result
            </button>
            <button 
              onClick={onReset}
              className="w-full py-3 px-4 bg-background hover:bg-muted text-foreground rounded-lg font-medium flex items-center justify-center gap-2 transition-colors border border-border"
            >
              <RefreshCcw className="w-5 h-5" />
              Process Another Image
            </button>
          </div>
        </div>
      </div>
    </div>
  );
}

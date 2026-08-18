import React from 'react';

export interface Detection {
  id: number;
  class: string;
  confidence: number;
  bbox: {
    x: number;
    y: number;
    width: number;
    height: number;
  };
}

interface DetectionTableProps {
  detections: Detection[];
}

export function DetectionTable({ detections }: DetectionTableProps) {
  if (detections.length === 0) return null;

  return (
    <div className="w-full max-w-4xl mx-auto mt-8 mb-16 animate-slide-up-fade">
      <div className="bg-card rounded-xl border border-border shadow-sm overflow-hidden">
        <div className="p-4 border-b border-border bg-muted/30">
          <h3 className="font-semibold">Detection Details</h3>
        </div>
        <div className="overflow-x-auto">
          <table className="w-full text-sm text-left">
            <thead className="text-xs text-muted-foreground uppercase bg-muted/50 border-b border-border">
              <tr>
                <th className="px-6 py-4 font-medium">Egg ID</th>
                <th className="px-6 py-4 font-medium">Confidence</th>
                <th className="px-6 py-4 font-medium">X</th>
                <th className="px-6 py-4 font-medium">Y</th>
                <th className="px-6 py-4 font-medium">Width</th>
                <th className="px-6 py-4 font-medium">Height</th>
              </tr>
            </thead>
            <tbody>
              {detections.map((detection, index) => (
                <tr 
                  key={detection.id} 
                  className={`border-b border-border hover:bg-muted/30 transition-colors ${index % 2 === 0 ? 'bg-background' : 'bg-muted/10'}`}
                >
                  <td className="px-6 py-3 font-medium">Egg {detection.id}</td>
                  <td className="px-6 py-3">
                    <div className="flex items-center gap-2">
                      <span className={`font-medium ${detection.confidence > 0.8 ? 'text-green-600' : 'text-amber-600'}`}>
                        {(detection.confidence * 100).toFixed(1)}%
                      </span>
                    </div>
                  </td>
                  <td className="px-6 py-3 text-muted-foreground">{detection.bbox.x}px</td>
                  <td className="px-6 py-3 text-muted-foreground">{detection.bbox.y}px</td>
                  <td className="px-6 py-3 text-muted-foreground">{detection.bbox.width}px</td>
                  <td className="px-6 py-3 text-muted-foreground">{detection.bbox.height}px</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      </div>
    </div>
  );
}

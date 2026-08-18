import React from 'react';
import { Settings2 } from 'lucide-react';

interface ControlPanelProps {
  confidenceThreshold: number;
  setConfidenceThreshold: (val: number) => void;
  disabled: boolean;
}

export function ControlPanel({ confidenceThreshold, setConfidenceThreshold, disabled }: ControlPanelProps) {
  
  return (
    <div className="w-full max-w-2xl mx-auto mt-6 bg-card border border-border rounded-xl p-6 shadow-sm">
      <div className="flex items-center gap-2 mb-4">
        <Settings2 className="w-5 h-5 text-primary" />
        <h3 className="font-semibold">Detection Settings</h3>
      </div>
      
      <div>
        <div className="flex justify-between items-center mb-2">
          <label className="text-sm font-medium text-foreground">Confidence Threshold</label>
          <span className="text-sm font-bold text-primary bg-primary/10 px-2 py-0.5 rounded">
            {confidenceThreshold.toFixed(2)}
          </span>
        </div>
        <p className="text-xs text-muted-foreground mb-4">
          Adjust the minimum confidence required to count an object as an egg.
          Lower values detect more objects but may increase false positives.
        </p>
        
        <input 
          type="range" 
          min="0.30" 
          max="0.90" 
          step="0.05"
          value={confidenceThreshold}
          onChange={(e) => setConfidenceThreshold(parseFloat(e.target.value))}
          disabled={disabled}
          className="w-full h-2 bg-muted rounded-lg appearance-none cursor-pointer accent-primary"
        />
        
        <div className="flex justify-between text-xs text-muted-foreground mt-2 px-1">
          <span>0.30</span>
          <span>0.60</span>
          <span>0.90</span>
        </div>
      </div>
    </div>
  );
}

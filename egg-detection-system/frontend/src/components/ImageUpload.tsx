import React, { useCallback, useState } from 'react';
import { UploadCloud, Image as ImageIcon, X } from 'lucide-react';

interface ImageUploadProps {
  onImageSelect: (file: File) => void;
  isLoading: boolean;
}

export function ImageUpload({ onImageSelect, isLoading }: ImageUploadProps) {
  const [dragActive, setDragActive] = useState(false);
  const [selectedFile, setSelectedFile] = useState<File | null>(null);
  const [preview, setPreview] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);

  const handleDrag = useCallback((e: React.DragEvent) => {
    e.preventDefault();
    e.stopPropagation();
    if (e.type === "dragenter" || e.type === "dragover") {
      setDragActive(true);
    } else if (e.type === "dragleave") {
      setDragActive(false);
    }
  }, []);

  const validateFile = (file: File) => {
    setError(null);
    if (!file.type.match('image/jpeg') && !file.type.match('image/png') && !file.type.match('image/jpg')) {
      setError("Please upload a valid JPG or PNG image.");
      return false;
    }
    if (file.size > 10 * 1024 * 1024) {
      setError("Image size should be less than 10MB.");
      return false;
    }
    return true;
  };

  const handleDrop = useCallback((e: React.DragEvent) => {
    e.preventDefault();
    e.stopPropagation();
    setDragActive(false);
    
    if (e.dataTransfer.files && e.dataTransfer.files[0]) {
      const file = e.dataTransfer.files[0];
      if (validateFile(file)) {
        handleFile(file);
      }
    }
  }, []);

  const handleChange = (e: React.ChangeEvent<HTMLInputElement>) => {
    e.preventDefault();
    if (e.target.files && e.target.files[0]) {
      const file = e.target.files[0];
      if (validateFile(file)) {
        handleFile(file);
      }
    }
  };

  const handleFile = (file: File) => {
    setSelectedFile(file);
    const objectUrl = URL.createObjectURL(file);
    setPreview(objectUrl);
  };

  const handleDetect = () => {
    if (selectedFile) {
      onImageSelect(selectedFile);
    }
  };

  const clearSelection = () => {
    setSelectedFile(null);
    setPreview(null);
    setError(null);
  };

  return (
    <div className="w-full max-w-2xl mx-auto mt-8 animate-slide-up-fade">
      {!preview ? (
        <div
          className={`relative border-2 border-dashed rounded-xl p-12 text-center transition-all ${
            dragActive ? 'border-primary bg-primary/5' : 'border-border bg-card hover:border-primary/50'
          }`}
          onDragEnter={handleDrag}
          onDragLeave={handleDrag}
          onDragOver={handleDrag}
          onDrop={handleDrop}
        >
          <input
            type="file"
            accept="image/jpeg, image/jpg, image/png"
            className="absolute inset-0 w-full h-full opacity-0 cursor-pointer"
            onChange={handleChange}
            disabled={isLoading}
          />
          <UploadCloud className="w-12 h-12 text-primary mx-auto mb-4" />
          <h3 className="text-xl font-semibold mb-2">Upload Egg Image</h3>
          <p className="text-muted-foreground mb-4">Drag and drop or click to browse</p>
          <p className="text-xs text-muted-foreground/80">Supports JPG, JPEG, PNG (Max 10MB)</p>
          
          {error && (
            <div className="mt-4 p-3 bg-destructive/10 text-destructive rounded-lg text-sm">
              {error}
            </div>
          )}
        </div>
      ) : (
        <div className="bg-card rounded-xl overflow-hidden border border-border shadow-sm">
          <div className="relative aspect-video bg-black/5 flex items-center justify-center overflow-hidden">
            <img 
              src={preview} 
              alt="Preview" 
              className="max-h-full max-w-full object-contain"
            />
            {!isLoading && (
              <button 
                onClick={clearSelection}
                className="absolute top-2 right-2 p-1 bg-black/50 hover:bg-black/70 text-white rounded-full backdrop-blur-sm transition-colors"
              >
                <X className="w-5 h-5" />
              </button>
            )}
          </div>
          <div className="p-4 flex items-center justify-between bg-card">
            <div className="flex items-center gap-3">
              <ImageIcon className="w-8 h-8 text-primary" />
              <div>
                <p className="text-sm font-medium truncate max-w-[200px]">{selectedFile?.name}</p>
                <p className="text-xs text-muted-foreground">
                  {(selectedFile!.size / (1024 * 1024)).toFixed(2)} MB
                </p>
              </div>
            </div>
            <button
              onClick={handleDetect}
              disabled={isLoading}
              className={`px-6 py-2.5 rounded-lg font-medium text-white shadow-sm transition-all flex items-center gap-2 ${
                isLoading ? 'bg-primary/70 cursor-not-allowed' : 'bg-primary hover:bg-primary/90 hover:shadow-md'
              }`}
            >
              {isLoading ? (
                <>
                  <div className="w-4 h-4 border-2 border-white/30 border-t-white rounded-full animate-spin" />
                  Detecting Eggs...
                </>
              ) : (
                'Detect Eggs'
              )}
            </button>
          </div>
        </div>
      )}
    </div>
  );
}

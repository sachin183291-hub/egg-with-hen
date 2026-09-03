import React, { useState } from 'react';
import { X, Upload, MapPin, Loader2, Image as ImageIcon, Camera } from 'lucide-react';
import toast from 'react-hot-toast';
import exifr from 'exifr';
import { evidenceApi } from '../services/api';

interface UploadEvidenceModalProps {
  onClose: () => void;
  onSuccess: () => void;
}

export default function UploadEvidenceModal({ onClose, onSuccess }: UploadEvidenceModalProps) {
  const [file, setFile] = useState<File | null>(null);
  const [previewUrl, setPreviewUrl] = useState<string | null>(null);
  const [location, setLocation] = useState<{ lat: number; lng: number; acc: number, date?: Date } | null>(null);
  const [loading, setLoading] = useState(false);
  const [locating, setLocating] = useState(false);

  const fetchAddress = async (lat: number, lng: number): Promise<string> => {
    try {
      const res = await fetch(`https://nominatim.openstreetmap.org/reverse?format=json&lat=${lat}&lon=${lng}`);
      const data = await res.json();
      return data.display_name || 'Unknown Location';
    } catch (e) {
      return 'Unknown Location';
    }
  };

  const applyGeoTagStamp = async (originalFile: File, lat: number, lng: number, captureDate: Date = new Date()): Promise<File> => {
    const address = await fetchAddress(lat, lng);
    
    // Map Tile Calculation
    const zoom = 15;
    const n = Math.pow(2, zoom);
    const exactX = (lng + 180) / 360 * n;
    const exactY = (1 - Math.log(Math.tan(lat * Math.PI / 180) + 1 / Math.cos(lat * Math.PI / 180)) / Math.PI) / 2 * n;
    const tileX = Math.floor(exactX);
    const tileY = Math.floor(exactY);
    const pixelX = (exactX - tileX) * 256;
    const pixelY = (exactY - tileY) * 256;
    
    const mapTileUrl = `https://tile.openstreetmap.org/${zoom}/${tileX}/${tileY}.png`;
    const mapImg = new Image();
    mapImg.crossOrigin = 'anonymous';
    await new Promise((res) => {
      mapImg.onload = res;
      mapImg.onerror = res;
      mapImg.src = mapTileUrl;
    });

    return new Promise((resolve, reject) => {
      const img = new Image();
      const objectUrl = URL.createObjectURL(originalFile);
      img.onload = () => {
        let drawWidth = img.width;
        let drawHeight = img.height;
        const MAX_DIM = 1920;
        if (drawWidth > MAX_DIM || drawHeight > MAX_DIM) {
          const ratio = Math.min(MAX_DIM / drawWidth, MAX_DIM / drawHeight);
          drawWidth = Math.floor(drawWidth * ratio);
          drawHeight = Math.floor(drawHeight * ratio);
        }

        const canvas = document.createElement('canvas');
        canvas.width = drawWidth;
        canvas.height = drawHeight;
        const ctx = canvas.getContext('2d');
        if (!ctx) return reject('No canvas context');
        
        ctx.drawImage(img, 0, 0, drawWidth, drawHeight);
        
        const barHeight = Math.max(100, drawHeight * 0.12);
        ctx.fillStyle = 'rgba(0, 0, 0, 0.6)';
        ctx.fillRect(0, drawHeight - barHeight, drawWidth, barHeight);
        
        if (mapImg.complete && mapImg.naturalWidth > 0) {
          ctx.drawImage(mapImg, 0, drawHeight - barHeight, barHeight, barHeight);
          const markerX = (pixelX / 256) * barHeight;
          const markerY = (pixelY / 256) * barHeight;
          ctx.fillStyle = 'red';
          ctx.beginPath();
          ctx.arc(markerX, drawHeight - barHeight + markerY, barHeight * 0.05, 0, Math.PI * 2);
          ctx.fill();
          ctx.strokeStyle = 'white';
          ctx.lineWidth = barHeight * 0.01;
          ctx.stroke();
        }

        ctx.fillStyle = 'white';
        const fontSize = Math.max(16, Math.floor(drawHeight * 0.025));
        ctx.font = `${fontSize}px sans-serif`;
        ctx.textBaseline = 'top';
        
        const margin = fontSize;
        const textStartX = barHeight + margin;
        const textY = drawHeight - barHeight + margin;
        
        const dateStr = captureDate.toLocaleString('en-IN', { timeZone: 'Asia/Kolkata' });
        ctx.fillText(`Address: ${address.substring(0, 80)}${address.length > 80 ? '...' : ''}`, textStartX, textY);
        ctx.fillText(`Lat: ${lat.toFixed(6)}  Lng: ${lng.toFixed(6)}`, textStartX, textY + fontSize * 1.5);
        ctx.fillText(`Time: ${dateStr}`, textStartX, textY + fontSize * 3);
        
        canvas.toBlob((blob) => {
          URL.revokeObjectURL(objectUrl);
          if (blob) {
            const newFile = new File([blob], `geotagged_${originalFile.name}`, { type: 'image/jpeg' });
            resolve(newFile);
          } else {
            reject('Failed to create blob');
          }
        }, 'image/jpeg', 0.85);
      };
      img.onerror = reject;
      img.src = objectUrl;
    });
  };

  const cameraInputRef = React.useRef<HTMLInputElement>(null);
  const fileInputRef = React.useRef<HTMLInputElement>(null);

  const handleFileSelect = async (e: React.ChangeEvent<HTMLInputElement>) => {
    const selectedFile = e.target.files?.[0] || null;
    if (previewUrl) URL.revokeObjectURL(previewUrl);
    setLocation(null);
    setFile(null);
    setPreviewUrl(null);
    
    if (selectedFile) {
      setLocating(true);
      let finalLat: number | null = null;
      let finalLng: number | null = null;
      let finalDate: Date = new Date();
      let locSource = 'none';
      try {
        const exifData = await exifr.parse(selectedFile);
        if (exifData && exifData.DateTimeOriginal) {
          finalDate = new Date(exifData.DateTimeOriginal);
        }
        const gps = await exifr.gps(selectedFile);
        if (gps && typeof gps.latitude === 'number' && typeof gps.longitude === 'number') {
          finalLat = gps.latitude;
          finalLng = gps.longitude;
          locSource = 'exif';
        }
      } catch (err) {
        console.error('EXIF Error:', err);
      }

      if (locSource === 'none' && navigator.geolocation) {
        try {
          const pos = await new Promise<GeolocationPosition>((resolve, reject) => {
            navigator.geolocation.getCurrentPosition(resolve, reject, { 
              enableHighAccuracy: true, 
              timeout: 15000,
              maximumAge: 0
            });
          });
          finalLat = pos.coords.latitude;
          finalLng = pos.coords.longitude;
          locSource = 'browser';
        } catch (err: any) {
          console.warn('Geolocation fallback failed:', err);
          let errorMsg = 'Failed to get live location.';
          if (err.code === 1) errorMsg = 'Location permission denied. Please allow GPS access.';
          if (err.code === 2) errorMsg = 'Location unavailable. Please turn on GPS/Location in your phone settings.';
          if (err.code === 3) errorMsg = 'Location request timed out. Please try again outside.';
          toast.error(errorMsg);
          setLocating(false);
          return;
        }
      }

      if (finalLat === null || finalLng === null) {
        toast.error('Could not determine location. Using fallback location for testing.');
        finalLat = 13.0827; // Default to Chennai
        finalLng = 80.2707;
        locSource = 'dummy';
      }

      try {
        const stampedFile = await applyGeoTagStamp(selectedFile, finalLat, finalLng, finalDate);
        setFile(stampedFile);
        setPreviewUrl(URL.createObjectURL(stampedFile));
        setLocation({ lat: finalLat, lng: finalLng, acc: locSource !== 'dummy' ? 5 : 10, date: finalDate });
        if (locSource === 'exif') toast.success('Applied Stamp with EXIF GPS');
        else if (locSource === 'browser') toast.success('Applied Stamp with Live GPS');
        else toast.error('Browser blocked GPS. Using fallback location.');
      } catch (error) {
        toast.error('Failed to apply GeoTag stamp');
      } finally {
        setLocating(false);
      }
    }
  };

  const computeHash = async (file: File): Promise<string> => {
    if (!window.crypto || !window.crypto.subtle) {
      return "WEB-DASHBOARD-HASH";
    }
    const buffer = await file.arrayBuffer();
    const hashBuffer = await crypto.subtle.digest('SHA-256', buffer);
    const hashArray = Array.from(new Uint8Array(hashBuffer));
    return hashArray.map(b => b.toString(16).padStart(2, '0')).join('');
  };

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    if (!file) return toast.error('Please select an image');
    if (!location) return toast.error('Please capture location first');

    setLoading(true);
    try {
      const hash = await computeHash(file);
      const metadata = {
        latitude: location.lat,
        longitude: location.lng,
        gps_accuracy_meters: location.acc,
        capture_timestamp: (location.date || new Date()).toISOString(),
        device_identifier: 'WEB-DASHBOARD',
        client_hash: hash,
      };

      const formData = new FormData();
      formData.append('file', file);
      formData.append('metadata_json', JSON.stringify(metadata));

      await evidenceApi.upload(formData);
      toast.success('Evidence uploaded successfully!');
      onSuccess();
    } catch (err: any) {
      toast.error(err.response?.data?.detail || err.message || 'Upload failed');
    } finally {
      setLoading(false);
    }
  };

  return (
    <div style={{ position:'fixed', top:0, left:0, right:0, bottom:0, background:'rgba(0,0,0,0.6)', zIndex:999, display:'flex', alignItems:'center', justifyContent:'center' }}>
      <div className="card" style={{ width: 400, maxWidth: '90%', position:'relative', padding: 24 }}>
        <button onClick={onClose} style={{ position:'absolute', top:16, right:16, background:'none', border:'none', cursor:'pointer', color:'var(--text-muted)' }}>
          <X size={20} />
        </button>
        <h2 style={{ marginTop:0, marginBottom:20, fontSize:20 }}>Upload Evidence</h2>
        <form onSubmit={handleSubmit} style={{ display:'flex', flexDirection:'column', gap:16 }}>
          <div>
            <label style={{ display:'block', marginBottom:8, fontSize:14, fontWeight:500 }}>Photo Source</label>
            <div style={{ display:'flex', gap: 12 }}>
               <button type="button" className="btn btn-secondary" onClick={() => cameraInputRef.current?.click()} style={{ flex: 1, display: 'flex', justifyContent: 'center', cursor: 'pointer', gap: '8px' }}>
                 <Camera size={16} /> Take Photo
               </button>
               <input ref={cameraInputRef} type="file" accept="image/*" capture="environment" onClick={(e) => { e.currentTarget.value = '' }} onChange={handleFileSelect} style={{ display: 'none' }} />
            </div>
            {previewUrl && (
              <div style={{ marginTop: 12, textAlign: 'center' }}>
                <img src={previewUrl} alt="Preview" style={{ maxWidth: '100%', maxHeight: 200, borderRadius: 8, objectFit: 'contain' }} />
                <div style={{ marginTop: 4, fontSize: 12, color: 'var(--text-muted)' }}>{file?.name}</div>
              </div>
            )}
          </div>
          <div>
            <label style={{ display:'block', marginBottom:8, fontSize:14, fontWeight:500 }}>GPS Location</label>
            <div style={{ display:'flex', gap:12, alignItems:'center' }}>
              {locating ? (
                <span style={{ fontSize:13, color:'var(--text-muted)', display:'flex', alignItems:'center', gap:4 }}><Loader2 size={14} className="spin" /> Extracting EXIF data...</span>
              ) : !location ? (
                <span style={{ fontSize:13, color:'var(--text-muted)' }}>No location. Please select a geotagged photo.</span>
              ) : null}
              {location && <span style={{ fontSize:13, color:'var(--success)', fontWeight:500 }}>Acquired ✓</span>}
            </div>
            {location && (
              <div style={{ fontSize: 12, color: 'var(--text-muted)', marginTop: 8 }}>
                {location.lat.toFixed(6)}, {location.lng.toFixed(6)}
              </div>
            )}
          </div>
          <div style={{ marginTop: 8 }}>
            <button type="submit" className="btn btn-primary" disabled={loading || !file || !location} style={{ width:'100%', justifyContent:'center' }}>
              {loading ? <Loader2 size={16} className="spin" /> : <Upload size={16} />}
              Upload Evidence
            </button>
          </div>
        </form>
      </div>
    </div>
  );
}

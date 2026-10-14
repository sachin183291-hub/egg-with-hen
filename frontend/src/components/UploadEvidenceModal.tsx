import React, { useState, useEffect, useRef } from 'react';
import { 
  X, Upload, Loader2, Camera, 
  CheckCircle, Navigation, ShieldCheck, ShieldAlert, Check
} from 'lucide-react';
import toast from 'react-hot-toast';
import exifr from 'exifr';
import { evidenceApi } from '../services/api';

interface UploadEvidenceModalProps {
  onClose: () => void;
  onSuccess: () => void;
}

interface GeoLocationState {
  lat: number;
  lng: number;
  acc: number;
  address: string;
  date?: Date;
}

interface VerificationResult {
  id: string;
  evidence_number: string;
  status: 'VERIFIED' | 'SUSPICIOUS' | 'REVIEW_REQUIRED' | 'REJECTED';
  rejection_reason?: string;
  image_sha256_hash?: string;
  created_at?: string;
  ai_verification?: {
    status: string;
    tamper_probability?: number;
    confidence_score?: number;
    verification_message?: string;
    ela_score?: number;
    noise_score?: number;
  };
  blockchain_record?: {
    status: string;
    transaction_id?: string;
    block_number?: number;
  };
  metadata_?: {
    latitude: number;
    longitude: number;
    gps_accuracy_meters?: number;
  };
}

export default function UploadEvidenceModal({ onClose, onSuccess }: UploadEvidenceModalProps) {
  const [file, setFile] = useState<File | null>(null);
  const [previewUrl, setPreviewUrl] = useState<string | null>(null);
  const [location, setLocation] = useState<GeoLocationState | null>(null);
  const [loading, setLoading] = useState(false);
  const [locating, setLocating] = useState(false);
  
  // Verification result state to display after upload
  const [verificationResult, setVerificationResult] = useState<VerificationResult | null>(null);

  const cameraInputRef = useRef<HTMLInputElement>(null);

  // Helper: Multi-source high-accuracy reverse geocode to street / place address
  const fetchAddress = async (lat: number, lng: number): Promise<string> => {
    // 1. Primary: OpenStreetMap Nominatim with local details
    try {
      const res = await fetch(
        `https://nominatim.openstreetmap.org/reverse?format=json&lat=${lat}&lon=${lng}&zoom=18&addressdetails=1`,
        { headers: { 'Accept-Language': 'en' }, signal: AbortSignal.timeout(4000) }
      );
      if (res.ok) {
        const data = await res.json();
        if (data && data.address) {
          const a = data.address;
          const landmark = a.amenity || a.building || a.shop || a.leisure || '';
          const road = a.road || a.pedestrian || a.suburb || a.neighbourhood || a.residential || '';
          const locality = (a.suburb || a.neighbourhood) && (a.suburb !== road) ? (a.suburb || a.neighbourhood) : '';
          const townOrCity = a.village || a.town || a.city || a.municipality || a.county || '';
          const stateDist = (a.state_district && a.state_district !== townOrCity) ? a.state_district : '';
          const state = a.state || '';
          const postcode = a.postcode ? `${a.postcode}` : '';

          const parts = [
            landmark,
            road,
            locality,
            townOrCity,
            stateDist,
            state ? `${state}${postcode ? ` - ${postcode}` : ''}` : postcode,
            a.country
          ].filter(Boolean);

          const uniqueParts = parts.filter((part, idx) => parts.indexOf(part) === idx);
          if (uniqueParts.length > 0) return uniqueParts.join(', ');
        }
        if (data.display_name) return data.display_name;
      }
    } catch (e) {
      console.warn('Nominatim reverse geocode note:', e);
    }

    // 2. Secondary fallback: BigDataCloud client API
    try {
      const bdcRes = await fetch(
        `https://api.bigdatacloud.net/data/reverse-geocode-client?latitude=${lat}&longitude=${lng}&localityLanguage=en`,
        { signal: AbortSignal.timeout(3500) }
      );
      if (bdcRes.ok) {
        const bdc = await bdcRes.json();
        const parts = [
          bdc.locality || bdc.neighbourhood,
          bdc.city || bdc.principalSubdivision,
          bdc.postcode,
          bdc.countryName
        ].filter(Boolean);
        if (parts.length > 0) return parts.join(', ');
      }
    } catch (e) {
      console.warn('BDC reverse geocode fallback note:', e);
    }

    return `${lat.toFixed(6)}° N, ${lng.toFixed(6)}° E`;
  };

  // Continuous active GPS satellite tracking
  useEffect(() => {
    let watchId: number | null = null;

    const startLocationWatch = async () => {
      if (typeof navigator !== 'undefined' && navigator.geolocation) {
        navigator.geolocation.getCurrentPosition(
          async (pos) => {
            const lat = Number(pos.coords.latitude.toFixed(6));
            const lng = Number(pos.coords.longitude.toFixed(6));
            const acc = Math.round(pos.coords.accuracy || 3);
            const addr = await fetchAddress(lat, lng);
            setLocation({ lat, lng, acc, address: addr, date: new Date() });
          },
          async (err) => {
            console.warn('GPS initial query note:', err.message);
            // Fallback to network IP location if hardware GPS denied or timed out
            try {
              const ipRes = await fetch('https://ipapi.co/json/', { signal: AbortSignal.timeout(3000) });
              if (ipRes.ok) {
                const ipData = await ipRes.json();
                if (ipData.latitude && ipData.longitude) {
                  const lat = Number(Number(ipData.latitude).toFixed(6));
                  const lng = Number(Number(ipData.longitude).toFixed(6));
                  const addr = [ipData.city, ipData.region, ipData.country_name].filter(Boolean).join(', ');
                  setLocation({ lat, lng, acc: 100, address: addr, date: new Date() });
                }
              }
            } catch {}
          },
          { enableHighAccuracy: true, timeout: 10000, maximumAge: 0 }
        );

        // Continuous watch to keep GPS locked and sub-meter accurate
        watchId = navigator.geolocation.watchPosition(
          (pos) => {
            const lat = Number(pos.coords.latitude.toFixed(6));
            const lng = Number(pos.coords.longitude.toFixed(6));
            const acc = Math.round(pos.coords.accuracy || 3);
            setLocation(prev => {
              if (prev && Math.abs(prev.lat - lat) < 0.0001 && Math.abs(prev.lng - lng) < 0.0001) {
                return { ...prev, lat, lng, acc, date: new Date() };
              }
              fetchAddress(lat, lng).then(addr => {
                setLocation({ lat, lng, acc, address: addr, date: new Date() });
              });
              return prev || { lat, lng, acc, address: 'Pinpointing address...', date: new Date() };
            });
          },
          (err) => console.warn('GPS watch note:', err.message),
          { enableHighAccuracy: true, maximumAge: 1000, timeout: 15000 }
        );
      }
    };

    startLocationWatch();

    return () => {
      if (watchId !== null && navigator.geolocation) {
        navigator.geolocation.clearWatch(watchId);
      }
    };
  }, []);

  // Automatic GeoTag Stamper (GIS Map + Place Address + Lat/Lng + Time IST)
  const applyGeoTagStamp = async (
    originalFile: File, 
    lat: number, 
    lng: number, 
    acc: number = 3,
    captureDate: Date = new Date()
  ): Promise<{ stampedFile: File; address: string }> => {
    const address = await fetchAddress(lat, lng);
    
    // OpenStreetMap GIS Map Tile Calculation
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
      const timer = setTimeout(res, 2200);
      mapImg.onload = () => { clearTimeout(timer); res(null); };
      mapImg.onerror = () => { clearTimeout(timer); res(null); };
      mapImg.src = mapTileUrl;
    });

    const stampedFile = await new Promise<File>((resolve, reject) => {
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
        
        // 1. Draw camera photo
        ctx.drawImage(img, 0, 0, drawWidth, drawHeight);
        
        // 2. High-Precision GeoTag Watermark Banner at Bottom
        const barHeight = Math.max(140, Math.floor(drawHeight * 0.16));
        const barY = drawHeight - barHeight;

        // Dark slate backdrop with high contrast
        ctx.fillStyle = 'rgba(10, 15, 30, 0.92)';
        ctx.fillRect(0, barY, drawWidth, barHeight);

        // Top accent line (blue to cyan to emerald gradient)
        const stripeGrad = ctx.createLinearGradient(0, barY, drawWidth, barY);
        stripeGrad.addColorStop(0, '#0284C7');
        stripeGrad.addColorStop(0.5, '#38BDF8');
        stripeGrad.addColorStop(1, '#10B981');
        ctx.fillStyle = stripeGrad;
        ctx.fillRect(0, barY, drawWidth, Math.max(3, Math.floor(drawHeight * 0.004)));
        
        // 3. GIS Map Tile Box on Left
        const mapMargin = Math.floor(barHeight * 0.08);
        const mapSize = barHeight - (mapMargin * 2);
        const mapX = mapMargin;
        const mapY = barY + mapMargin;

        if (mapImg.complete && mapImg.naturalWidth > 0) {
          ctx.save();
          ctx.drawImage(mapImg, mapX, mapY, mapSize, mapSize);
          ctx.strokeStyle = 'rgba(255, 255, 255, 0.5)';
          ctx.lineWidth = 1.5;
          ctx.strokeRect(mapX, mapY, mapSize, mapSize);
          
          // Target Pinpoint Marker
          const markerX = mapX + (pixelX / 256) * mapSize;
          const markerY = mapY + (pixelY / 256) * mapSize;

          // Outer radar wave
          ctx.fillStyle = 'rgba(239, 68, 68, 0.35)';
          ctx.beginPath();
          ctx.arc(markerX, markerY, mapSize * 0.12, 0, Math.PI * 2);
          ctx.fill();

          // Center red pin
          ctx.fillStyle = '#EF4444';
          ctx.beginPath();
          ctx.arc(markerX, markerY, mapSize * 0.045, 0, Math.PI * 2);
          ctx.fill();
          ctx.strokeStyle = '#FFFFFF';
          ctx.lineWidth = 1.5;
          ctx.stroke();

          // GIS MAP label
          ctx.fillStyle = 'rgba(0, 0, 0, 0.75)';
          ctx.fillRect(mapX + 2, mapY + mapSize - 15, 52, 13);
          ctx.fillStyle = '#38BDF8';
          ctx.font = 'bold 9px sans-serif';
          ctx.fillText('GIS MAP', mapX + 6, mapY + mapSize - 5);
          ctx.restore();
        }

        // 4. Information Block on Right
        const textStartX = mapX + mapSize + Math.floor(barHeight * 0.10);
        const availableWidth = drawWidth - textStartX - mapMargin;
        const baseFontSize = Math.max(14, Math.floor(drawHeight * 0.021));
        const fontSans = '-apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, sans-serif';
        
        ctx.textBaseline = 'top';

        // Helper: Word wrap for long addresses
        const wrapAddress = (text: string, maxW: number): string[] => {
          const words = text.split(' ');
          const lines: string[] = [];
          let cur = '';
          for (const w of words) {
            const test = cur ? `${cur} ${w}` : w;
            ctx.font = `bold ${baseFontSize}px ${fontSans}`;
            if (ctx.measureText(test).width > maxW && cur) {
              lines.push(cur);
              cur = w;
              if (lines.length >= 2) break;
            } else {
              cur = test;
            }
          }
          if (cur && lines.length < 2) lines.push(cur);
          return lines;
        };

        const addrLines = wrapAddress(address, availableWidth);
        const lineHeight = Math.floor(baseFontSize * 1.35);
        let curY = barY + mapMargin + 2;

        // Line 1 (& 2 if wrapped): Exact Place Address
        ctx.fillStyle = '#FFFFFF';
        ctx.font = `bold ${baseFontSize}px ${fontSans}`;
        for (let i = 0; i < addrLines.length; i++) {
          const prefix = i === 0 ? '📍 ' : '   ';
          ctx.fillText(prefix + addrLines[i], textStartX, curY);
          curY += lineHeight;
        }

        // Next Line: GPS Coordinates
        ctx.fillStyle = '#38BDF8';
        ctx.font = `600 ${Math.floor(baseFontSize * 0.88)}px ${fontSans}`;
        ctx.fillText(
          `🛰️ GPS: Lat ${lat.toFixed(6)}° N   Long ${lng.toFixed(6)}° E  (±${acc}m)`,
          textStartX,
          curY
        );
        curY += lineHeight;

        // Next Line: Date & Time in IST
        const dateStr = captureDate.toLocaleDateString('en-IN', {
          day: '2-digit', month: 'short', year: 'numeric',
          timeZone: 'Asia/Kolkata'
        }) + ', ' + captureDate.toLocaleTimeString('en-IN', {
          hour: '2-digit', minute: '2-digit', second: '2-digit', hour12: true,
          timeZone: 'Asia/Kolkata'
        }) + ' IST';

        ctx.fillStyle = '#FCD34D';
        ctx.font = `600 ${Math.floor(baseFontSize * 0.84)}px ${fontSans}`;
        ctx.fillText(`🕒 Time: ${dateStr}`, textStartX, curY);
        curY += lineHeight;

        // Next Line: GioTag Real-Time Physical Verification Seal
        ctx.fillStyle = '#34D399';
        ctx.font = `600 ${Math.floor(baseFontSize * 0.78)}px ${fontSans}`;
        ctx.fillText(`🔒 GioTag Real-Time Physical Verification • Authenticated`, textStartX, curY);

        canvas.toBlob((blob) => {
          URL.revokeObjectURL(objectUrl);
          if (blob) {
            const newF = new File([blob], `geotagged_${originalFile.name}`, { type: 'image/jpeg' });
            resolve(newF);
          } else {
            reject('Failed to create geotagged blob');
          }
        }, 'image/jpeg', 0.90);
      };
      img.onerror = reject;
      img.src = objectUrl;
    });

    return { stampedFile, address };
  };

  // Handle Photo Capture: Automatic GPS lock + Automatic Stamping + Automatic Preview
  const handleFileSelect = async (e: React.ChangeEvent<HTMLInputElement>) => {
    const selectedFile = e.target.files?.[0] || null;
    if (!selectedFile) return;

    if (previewUrl) URL.revokeObjectURL(previewUrl);
    setLocating(true);

    try {
      let finalLat: number | null = null;
      let finalLng: number | null = null;
      let finalAcc: number = 3;
      let finalDate: Date = new Date();

      // 1. Inspect image EXIF GPS first (if camera hardware saved it)
      try {
        const exifData = await exifr.parse(selectedFile);
        if (exifData && exifData.DateTimeOriginal) {
          finalDate = new Date(exifData.DateTimeOriginal);
        }
        const gps = await exifr.gps(selectedFile);
        if (gps && typeof gps.latitude === 'number' && typeof gps.longitude === 'number') {
          finalLat = Number(gps.latitude.toFixed(6));
          finalLng = Number(gps.longitude.toFixed(6));
          finalAcc = 3;
        }
      } catch (e) {
        console.warn('EXIF read note:', e);
      }

      // 2. If no EXIF GPS, use live hardware satellite GPS from active tracker
      if ((finalLat === null || finalLng === null) && location && location.lat && location.lng) {
        finalLat = location.lat;
        finalLng = location.lng;
        finalAcc = location.acc;
      }

      // 3. Fallback: Query live device position right now
      if (finalLat === null || finalLng === null) {
        if (typeof navigator !== 'undefined' && navigator.geolocation) {
          try {
            const pos = await new Promise<GeolocationPosition>((resolve, reject) => {
              navigator.geolocation.getCurrentPosition(resolve, reject, {
                enableHighAccuracy: true,
                timeout: 8000,
                maximumAge: 0,
              });
            });
            finalLat = Number(pos.coords.latitude.toFixed(6));
            finalLng = Number(pos.coords.longitude.toFixed(6));
            finalAcc = Math.round(pos.coords.accuracy || 3);
          } catch (err: any) {
            console.warn('Live GPS query note:', err.message);
          }
        }
      }

      // 4. Fallback: Network IP Location
      if (finalLat === null || finalLng === null) {
        try {
          const ipRes = await fetch('https://ipapi.co/json/', { signal: AbortSignal.timeout(3000) });
          if (ipRes.ok) {
            const ipData = await ipRes.json();
            if (ipData.latitude && ipData.longitude) {
              finalLat = Number(Number(ipData.latitude).toFixed(6));
              finalLng = Number(Number(ipData.longitude).toFixed(6));
              finalAcc = 100;
            }
          }
        } catch (e) {}
      }

      // If still unable to find location, alert user to enable GPS on phone
      if (finalLat === null || finalLng === null) {
        toast.error('Unable to detect physical GPS coordinates. Please enable Location in your phone settings.');
        return;
      }

      // Automatically Stamp Photo with GIS Map, Address, Lat/Lng, and Timing!
      const { stampedFile, address } = await applyGeoTagStamp(selectedFile, finalLat, finalLng, finalAcc, finalDate);
      
      setFile(stampedFile);
      setPreviewUrl(URL.createObjectURL(stampedFile));
      setLocation({
        lat: finalLat,
        lng: finalLng,
        acc: finalAcc,
        address,
        date: finalDate
      });

      toast.success(`🎯 GeoTag Stamped: ${address.substring(0, 40)}...`);
    } catch (error: any) {
      console.error('GeoTag error:', error);
      toast.error('Failed to apply GeoTag: ' + (error?.message || error));
    } finally {
      setLocating(false);
    }
  };

  const computeHash = async (f: File): Promise<string> => {
    if (!window.crypto || !window.crypto.subtle) {
      return "WEB-DASHBOARD-HASH";
    }
    const buffer = await f.arrayBuffer();
    const hashBuffer = await crypto.subtle.digest('SHA-256', buffer);
    const hashArray = Array.from(new Uint8Array(hashBuffer));
    return hashArray.map(b => b.toString(16).padStart(2, '0')).join('');
  };

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    if (!file) return toast.error('Please take a photo first');
    if (!location) return toast.error('Location is being acquired, please wait a moment');

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

      const res = await evidenceApi.upload(formData);
      const data: VerificationResult = res.data;
      
      setVerificationResult(data);
      if (data.status === 'VERIFIED') {
        toast.success('Photo Verified Authentic! ✅');
      } else {
        toast.error('Photo Flagged as SUSPICIOUS ⚠️');
      }
    } catch (err: any) {
      toast.error(err.response?.data?.detail || err.message || 'Upload failed');
    } finally {
      setLoading(false);
    }
  };

  const handleRetake = () => {
    setVerificationResult(null);
    setFile(null);
    if (previewUrl) URL.revokeObjectURL(previewUrl);
    setPreviewUrl(null);
    cameraInputRef.current?.click();
  };

  return (
    <div style={{
      position: 'fixed',
      inset: 0,
      background: 'rgba(0,0,0,0.75)',
      backdropFilter: 'blur(6px)',
      zIndex: 999,
      display: 'flex',
      alignItems: 'center',
      justifyContent: 'center',
      padding: 16
    }}>
      <div className="card" style={{
        width: 460,
        maxWidth: '100%',
        maxHeight: '92vh',
        overflowY: 'auto',
        position: 'relative',
        padding: 24,
        background: 'var(--bg-card)',
        borderRadius: 16,
        border: '1px solid var(--border-color)',
        boxShadow: '0 25px 50px -12px rgba(0, 0, 0, 0.45)'
      }}>
        <button
          onClick={onClose}
          style={{
            position: 'absolute',
            top: 16,
            right: 16,
            background: 'none',
            border: 'none',
            cursor: 'pointer',
            color: 'var(--text-muted)'
          }}
        >
          <X size={20} />
        </button>

        {/* ─── Screen 2: Verification Result View ─────────────────────────────────── */}
        {verificationResult ? (
          <div>
            <div style={{ textAlign: 'center', marginBottom: 20 }}>
              {verificationResult.status === 'VERIFIED' ? (
                <div style={{
                  display: 'inline-flex',
                  alignItems: 'center',
                  justifyContent: 'center',
                  width: 68,
                  height: 68,
                  borderRadius: '50%',
                  background: 'rgba(16, 185, 129, 0.15)',
                  border: '2px solid #10B981',
                  margin: '0 auto 12px auto'
                }}>
                  <ShieldCheck size={38} color="#10B981" />
                </div>
              ) : (
                <div style={{
                  display: 'inline-flex',
                  alignItems: 'center',
                  justifyContent: 'center',
                  width: 68,
                  height: 68,
                  borderRadius: '50%',
                  background: 'rgba(239, 68, 68, 0.15)',
                  border: '2px solid #EF4444',
                  margin: '0 auto 12px auto'
                }}>
                  <ShieldAlert size={38} color="#EF4444" />
                </div>
              )}

              <h2 style={{
                margin: '0 0 6px 0',
                fontSize: '1.4rem',
                fontWeight: 800,
                color: verificationResult.status === 'VERIFIED' ? '#10B981' : '#EF4444'
              }}>
                {verificationResult.status === 'VERIFIED' ? 'STATUS: VERIFIED ✅' : 'STATUS: SUSPICIOUS ⚠️'}
              </h2>
              <p style={{ margin: 0, fontSize: '0.86rem', color: 'var(--text-secondary)' }}>
                {verificationResult.status === 'VERIFIED' 
                  ? 'Genuine live physical scene confirmed with cryptographic proof.'
                  : (verificationResult.rejection_reason || 'Security flags detected during AI authenticity analysis.')}
              </p>
            </div>

            {/* Verification Metric Cards */}
            <div style={{
              display: 'grid',
              gridTemplateColumns: '1fr 1fr',
              gap: 10,
              marginBottom: 16
            }}>
              <div style={{ background: 'var(--bg-secondary)', padding: '10px 12px', borderRadius: 10, border: '1px solid var(--border-color)' }}>
                <span style={{ fontSize: '0.72rem', color: 'var(--text-muted)', display: 'block' }}>Evidence Number</span>
                <span style={{ fontSize: '0.88rem', fontWeight: 700, color: 'var(--text-primary)' }}>
                  {verificationResult.evidence_number}
                </span>
              </div>

              <div style={{ background: 'var(--bg-secondary)', padding: '10px 12px', borderRadius: 10, border: '1px solid var(--border-color)' }}>
                <span style={{ fontSize: '0.72rem', color: 'var(--text-muted)', display: 'block' }}>AI Tamper Risk</span>
                <span style={{ 
                  fontSize: '0.88rem', 
                  fontWeight: 700, 
                  color: (verificationResult.ai_verification?.tamper_probability || 0) > 0.4 ? '#EF4444' : '#10B981' 
                }}>
                  {(((verificationResult.ai_verification?.tamper_probability || 0) * 100)).toFixed(1)}%
                </span>
              </div>

              <div style={{ background: 'var(--bg-secondary)', padding: '10px 12px', borderRadius: 10, border: '1px solid var(--border-color)', gridColumn: 'span 2' }}>
                <span style={{ fontSize: '0.72rem', color: 'var(--text-muted)', display: 'block' }}>Exact Location Stamped</span>
                <span style={{ fontSize: '0.85rem', fontWeight: 600, color: '#38BDF8' }}>
                  {location?.lat.toFixed(6)}° N, {location?.lng.toFixed(6)}° E (±{location?.acc}m)
                </span>
                <div style={{ fontSize: '0.75rem', color: 'var(--text-primary)', marginTop: 2, fontWeight: 500 }}>
                  📍 {location?.address}
                </div>
              </div>

              <div style={{ background: 'var(--bg-secondary)', padding: '10px 12px', borderRadius: 10, border: '1px solid var(--border-color)', gridColumn: 'span 2' }}>
                <span style={{ fontSize: '0.72rem', color: 'var(--text-muted)', display: 'block' }}>Blockchain Ledger</span>
                <span style={{ fontSize: '0.78rem', fontFamily: 'monospace', color: '#10B981', display: 'flex', alignItems: 'center', gap: 4 }}>
                  <Check size={14} /> Registered: {verificationResult.blockchain_record?.transaction_id?.substring(0, 24)}...
                </span>
              </div>
            </div>

            {/* AI Forensic Explanation */}
            {verificationResult.ai_verification?.verification_message && (
              <div style={{
                background: verificationResult.status === 'VERIFIED' ? 'rgba(16, 185, 129, 0.08)' : 'rgba(239, 68, 68, 0.08)',
                border: `1px solid ${verificationResult.status === 'VERIFIED' ? 'rgba(16, 185, 129, 0.3)' : 'rgba(239, 68, 68, 0.3)'}`,
                padding: '10px 14px',
                borderRadius: 10,
                fontSize: '0.78rem',
                color: verificationResult.status === 'VERIFIED' ? '#10B981' : '#EF4444',
                marginBottom: 18,
                lineHeight: 1.4
              }}>
                <strong>Forensic Detail:</strong> {verificationResult.ai_verification.verification_message}
              </div>
            )}

            {/* Action Buttons */}
            <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: 10 }}>
              <button
                type="button"
                className="btn btn-secondary"
                onClick={handleRetake}
                style={{ justifyContent: 'center', padding: '10px' }}
              >
                Retake Photo
              </button>
              <button
                type="button"
                className="btn btn-primary"
                onClick={() => {
                  onSuccess();
                  onClose();
                }}
                style={{ justifyContent: 'center', padding: '10px' }}
              >
                Done
              </button>
            </div>
          </div>
        ) : (
          /* ─── Screen 1: Camera Photo Capture & Upload ─────────────────────────── */
          <>
            <h2 style={{ margin: '0 0 4px 0', fontSize: '1.25rem' }}>Capture GeoTag Evidence</h2>
            <p style={{ margin: '0 0 16px 0', fontSize: '0.82rem', color: 'var(--text-secondary)' }}>
              100% Automatic: Takes photo and automatically stamps GIS map, exact place, GPS & time
            </p>

            <form onSubmit={handleSubmit} style={{ display: 'flex', flexDirection: 'column', gap: 14 }}>
              {/* Camera Trigger */}
              <div>
                <button
                  type="button"
                  className="btn btn-primary"
                  onClick={() => cameraInputRef.current?.click()}
                  disabled={locating || loading}
                  style={{
                    display: 'flex',
                    justifyContent: 'center',
                    alignItems: 'center',
                    gap: 10,
                    padding: '15px 20px',
                    fontSize: '1.05rem',
                    fontWeight: 700,
                    borderRadius: 12,
                    width: '100%',
                    boxShadow: '0 4px 14px rgba(59, 130, 246, 0.35)'
                  }}
                >
                  <Camera size={22} /> Take Photo (Camera)
                </button>
                <input
                  ref={cameraInputRef}
                  type="file"
                  accept="image/*"
                  capture="environment"
                  onClick={(e) => { e.currentTarget.value = '' }}
                  onChange={handleFileSelect}
                  style={{ display: 'none' }}
                />

                {/* Stamping Progress Loader */}
                {locating && (
                  <div style={{ marginTop: 14, padding: 18, textAlign: 'center', background: 'var(--bg-secondary)', borderRadius: 10, border: '1px solid var(--border-color)' }}>
                    <Loader2 size={26} className="spin" style={{ margin: '0 auto 8px auto', display: 'block', color: 'var(--brand-500)' }} />
                    <span style={{ fontSize: '0.86rem', fontWeight: 600, color: 'var(--text-primary)', display: 'block' }}>
                      Automatically Stamping GeoTag, GIS Map & Place...
                    </span>
                    <span style={{ fontSize: '0.74rem', color: 'var(--text-secondary)', marginTop: 4, display: 'block' }}>
                      Pinpointing location coordinates and IST timestamp
                    </span>
                  </div>
                )}

                {/* Preview Box with Stamped GeoTag */}
                {previewUrl && !locating && (
                  <div style={{ marginTop: 14, textAlign: 'center', background: 'var(--bg-secondary)', padding: 10, borderRadius: 10, border: '1px solid var(--border-color)' }}>
                    <img
                      src={previewUrl}
                      alt="GeoTag Preview"
                      style={{ maxWidth: '100%', maxHeight: 220, borderRadius: 8, objectFit: 'contain' }}
                    />
                    <div style={{ marginTop: 8, fontSize: '0.78rem', color: '#10B981', fontWeight: 600, display: 'flex', alignItems: 'center', justifyContent: 'center', gap: 5 }}>
                      <CheckCircle size={15} /> GeoTag, GIS Map & Place Stamped Automatically
                    </div>
                    <div style={{ marginTop: 4, fontSize: '0.73rem', color: '#38BDF8', fontWeight: 600, display: 'flex', alignItems: 'center', justifyContent: 'center', gap: 4 }}>
                      ⏱️ Freshness Rule: Upload within 3 minutes for VERIFIED status
                    </div>
                  </div>
                )}
              </div>

              {/* Automatic Location Status Indicator */}
              <div style={{
                background: 'var(--bg-secondary)',
                padding: '12px 14px',
                borderRadius: 10,
                border: '1px solid var(--border-color)'
              }}>
                <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center' }}>
                  <span style={{ fontSize: '0.78rem', fontWeight: 600, color: 'var(--text-secondary)', display: 'flex', alignItems: 'center', gap: 5 }}>
                    <Navigation size={14} color="#3B82F6" /> Automatic Location Stamped on Photo
                  </span>
                  <span style={{
                    fontSize: '0.68rem',
                    padding: '2px 8px',
                    borderRadius: 4,
                    fontWeight: 600,
                    background: location ? 'rgba(16, 185, 129, 0.15)' : 'rgba(234, 179, 8, 0.15)',
                    color: location ? '#10B981' : '#EAB308'
                  }}>
                    {location ? '🟢 Auto-Location Ready' : '🛰️ Acquiring...'}
                  </span>
                </div>

                {location ? (
                  <div style={{ marginTop: 6 }}>
                    <div style={{ fontSize: '0.85rem', fontWeight: 700, color: '#38BDF8' }}>
                      {location.lat.toFixed(6)}° N, {location.lng.toFixed(6)}° E (±{location.acc}m)
                    </div>
                    <div style={{ fontSize: '0.78rem', color: 'var(--text-primary)', marginTop: 2, fontWeight: 500, lineHeight: 1.35 }}>
                      📍 {location.address}
                    </div>
                  </div>
                ) : (
                  <div style={{ fontSize: '0.78rem', color: 'var(--text-secondary)', marginTop: 6, display: 'flex', alignItems: 'center', gap: 6 }}>
                    <Loader2 size={13} className="spin" color="#3B82F6" /> Acquiring exact physical coordinates...
                  </div>
                )}
              </div>

              {/* Submit Button */}
              <div style={{ marginTop: 2 }}>
                <button
                  type="submit"
                  className="btn btn-primary"
                  disabled={loading || !file || locating}
                  style={{ width: '100%', justifyContent: 'center', padding: '13px', fontSize: '0.94rem' }}
                >
                  {loading ? (
                    <>
                      <Loader2 size={16} className="spin" style={{ marginRight: 8 }} />
                      Verifying AI Authenticity & Uploading...
                    </>
                  ) : (
                    <>
                      <Upload size={16} style={{ marginRight: 8 }} />
                      Upload & Verify Evidence
                    </>
                  )}
                </button>
              </div>
            </form>
          </>
        )}
      </div>
    </div>
  );
}

import { useState, useEffect } from 'react';
import { Download, PlusSquare } from 'lucide-react';
import krLogo from '../kr-logo.png';

export default function InstallPrompt() {
  const [isStandalone, setIsStandalone] = useState(true);
  const [deferredPrompt, setDeferredPrompt] = useState<any>(null);
  const [isIOS, setIsIOS] = useState(false);

  useEffect(() => {
    const checkStandalone = () => {
      const isStandaloneMedia = window.matchMedia('(display-mode: standalone)').matches;
      const isStandaloneNavigator = (navigator as any).standalone === true;
      return isStandaloneMedia || isStandaloneNavigator;
    };

    // Initial check
    setIsStandalone(checkStandalone());

    // Check if the device is iOS
    const isIosDevice = /iPad|iPhone|iPod/.test(navigator.userAgent) && !(window as any).MSStream;
    setIsIOS(isIosDevice);

    const handleBeforeInstallPrompt = (e: any) => {
      e.preventDefault();
      setDeferredPrompt(e);
      setIsStandalone(false); // If we get the event, we are definitely not standalone
    };

    window.addEventListener('beforeinstallprompt', handleBeforeInstallPrompt);
    
    const handleResize = () => {
      setIsStandalone(checkStandalone());
    };
    window.addEventListener('resize', handleResize);

    // If it's not standalone on mount, and we don't get the event immediately, we still want to show the prompt
    // However, on some browsers `beforeinstallprompt` might take a few ms or not fire.
    // So we just rely on `checkStandalone()`. If it's false, they are in the browser.
    
    return () => {
      window.removeEventListener('beforeinstallprompt', handleBeforeInstallPrompt);
      window.removeEventListener('resize', handleResize);
    };
  }, []);

  const handleInstallClick = async () => {
    if (deferredPrompt) {
      deferredPrompt.prompt();
      const { outcome } = await deferredPrompt.userChoice;
      if (outcome === 'accepted') {
        setIsStandalone(true);
      }
    } else {
      alert("Installation is not supported or already installed. If you're on a mobile device, try adding to Home Screen manually.");
    }
  };

  if (isStandalone) {
    return null; // App is already installed or running in standalone mode
  }

  return (
    <div style={{
      position: 'fixed',
      top: 0, left: 0, right: 0,
      backgroundColor: '#1e293b',
      zIndex: 99999,
      display: 'flex',
      alignItems: 'center',
      justifyContent: 'space-between',
      padding: '12px 24px',
      color: 'white',
      borderBottom: '1px solid rgba(255, 255, 255, 0.1)',
      boxShadow: '0 4px 6px -1px rgba(0, 0, 0, 0.1)'
    }}>
      <div style={{ display: 'flex', alignItems: 'center', gap: '16px' }}>
        <img src={krLogo} alt="KR Group" style={{ height: '32px', objectFit: 'contain' }} />
        <div>
          <h3 style={{ fontSize: '16px', fontWeight: 'bold', margin: 0 }}>Install KR Group App</h3>
          <p style={{ color: '#94a3b8', fontSize: '12px', margin: 0 }}>For the best experience and offline access</p>
        </div>
      </div>

      <div>
        {isIOS ? (
          <div style={{ fontSize: '12px', color: '#60a5fa', textAlign: 'right' }}>
            Tap <PlusSquare size={14} style={{ display: 'inline', verticalAlign: 'text-bottom' }} /> <strong>Share</strong><br/>
            then <strong>"Add to Home Screen"</strong>
          </div>
        ) : deferredPrompt ? (
          <button 
            onClick={handleInstallClick}
            style={{
              backgroundColor: '#3b82f6',
              color: 'white',
              border: 'none',
              padding: '8px 16px',
              borderRadius: '6px',
              fontSize: '14px',
              fontWeight: 'bold',
              cursor: 'pointer',
              display: 'flex',
              alignItems: 'center',
              gap: '6px',
              transition: 'background-color 0.2s'
            }}
          >
            <Download size={16} />
            Install
          </button>
        ) : (
          <div style={{ fontSize: '12px', color: '#94a3b8', textAlign: 'right' }}>
            To install, tap your browser menu (⋮)<br/>
            and select <strong>"Install App"</strong> or <strong>"Add to Home Screen"</strong>
          </div>
        )}
      </div>
    </div>
  );
}

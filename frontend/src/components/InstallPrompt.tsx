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
      top: 0, left: 0, right: 0, bottom: 0,
      backgroundColor: 'rgba(15, 23, 42, 0.95)',
      backdropFilter: 'blur(10px)',
      zIndex: 99999,
      display: 'flex',
      flexDirection: 'column',
      alignItems: 'center',
      justifyContent: 'center',
      padding: '24px',
      textAlign: 'center',
      color: 'white'
    }}>
      <div style={{
        backgroundColor: '#1e293b',
        padding: '40px 32px',
        borderRadius: '16px',
        maxWidth: '400px',
        width: '100%',
        boxShadow: '0 25px 50px -12px rgba(0, 0, 0, 0.5)',
        border: '1px solid rgba(255, 255, 255, 0.1)',
        display: 'flex',
        flexDirection: 'column',
        alignItems: 'center'
      }}>
        <img src={krLogo} alt="KR Group" style={{ height: '64px', marginBottom: '24px', objectFit: 'contain' }} />
        <h2 style={{ fontSize: '24px', fontWeight: 'bold', marginBottom: '12px' }}>Install App Required</h2>
        <p style={{ color: '#94a3b8', marginBottom: '32px', lineHeight: '1.6' }}>
          For the best experience, offline access, and full features, please install the KR Group Poultry application on your device to continue.
        </p>

        {isIOS ? (
          <div style={{ backgroundColor: 'rgba(59, 130, 246, 0.1)', border: '1px solid rgba(59, 130, 246, 0.3)', padding: '16px', borderRadius: '8px', color: '#60a5fa', fontSize: '14px', display: 'flex', flexDirection: 'column', gap: '8px', textAlign: 'left', width: '100%' }}>
            <p style={{ margin: 0 }}><strong>To install on iOS:</strong></p>
            <p style={{ margin: 0 }}>1. Tap the <PlusSquare size={16} style={{ display: 'inline', verticalAlign: 'text-bottom' }} /> <strong>Share</strong> button.</p>
            <p style={{ margin: 0 }}>2. Select <strong>"Add to Home Screen"</strong>.</p>
          </div>
        ) : (
          <button 
            onClick={handleInstallClick}
            style={{
              backgroundColor: '#3b82f6',
              color: 'white',
              border: 'none',
              padding: '14px 24px',
              borderRadius: '8px',
              fontSize: '16px',
              fontWeight: 'bold',
              cursor: 'pointer',
              display: 'flex',
              alignItems: 'center',
              gap: '8px',
              width: '100%',
              justifyContent: 'center',
              transition: 'background-color 0.2s'
            }}
            onMouseOver={(e) => (e.currentTarget.style.backgroundColor = '#2563eb')}
            onMouseOut={(e) => (e.currentTarget.style.backgroundColor = '#3b82f6')}
          >
            <Download size={20} />
            Install Application Now
          </button>
        )}
      </div>
    </div>
  );
}

import { defineConfig, loadEnv } from 'vite'
import react from '@vitejs/plugin-react'
import { VitePWA } from 'vite-plugin-pwa'
import basicSsl from '@vitejs/plugin-basic-ssl'

export default defineConfig(({ mode }) => {
  const env = loadEnv(mode, process.cwd(), '')
  
  return {
    plugins: [
      react(),
      basicSsl(),
      VitePWA({
        registerType: 'autoUpdate',
        includeAssets: ['favicon.svg', 'kr-logo.png', 'bg-image.png'],
        manifest: {
          name: 'GioTag Egg Counter',
          short_name: 'GioTag',
          description: 'Secure Evidence Management and AI Egg Detection',
          theme_color: '#ffffff',
          background_color: '#f8fafc',
          display: 'standalone',
          icons: [
            {
              src: 'kr-logo.png',
              sizes: '192x192',
              type: 'image/png'
            },
            {
              src: 'kr-logo.png',
              sizes: '512x512',
              type: 'image/png'
            }
          ]
        }
      })
    ],
    server: {
      host: true,
      port: 5173,
      proxy: {
        '/api': {
          target: env.VITE_API_URL || 'http://127.0.0.1:8000',
          changeOrigin: true,
        },
        '/uploads': {
          target: env.VITE_API_URL || 'http://127.0.0.1:8000',
          changeOrigin: true,
        },
      },
    },
  }
})

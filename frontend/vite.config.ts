import { defineConfig } from 'vite'
import react from '@vitejs/plugin-react'

// https://vite.dev/config/
export default defineConfig({
  plugins: [react()],
  server: {
    port: 5173,
    strictPort: true,
    // 브라우저가 Render를 직접 호출하지 않게 해 localhost/127.0.0.1 CORS 차이를 없앤다.
    proxy: {
      '/scenario': { target: 'https://lastsight-ai.onrender.com', changeOrigin: true },
      '/ppe-violations': { target: 'https://lastsight-ai.onrender.com', changeOrigin: true },
      '/zone-maps': { target: 'https://lastsight-ai.onrender.com', changeOrigin: true },
      '/situation-chat': { target: 'https://lastsight-ai.onrender.com', changeOrigin: true },
      '/demo-frames': { target: 'https://lastsight-ai.onrender.com', changeOrigin: true },
      '/ws': { target: 'wss://lastsight-ai.onrender.com', ws: true, changeOrigin: true },
    },
  },
})

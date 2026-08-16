import { defineConfig } from 'vite'
import react from '@vitejs/plugin-react'

// https://vite.dev/config/
export default defineConfig({
  plugins: [react()],
  server: {
    port: 3004,
    strictPort: true,
    // Proxy API calls to the FastAPI backend so the frontend can use relative
    // /api/... URLs. Avoids any CORS configuration on the server side.
    proxy: {
      '/api': 'http://127.0.0.1:8019',
    },
  },
})

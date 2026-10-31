import react from '@vitejs/plugin-react'
import { defineConfig } from 'vite'

// https://vite.dev/config/
export default defineConfig({
  plugins: [react()],
  server: {
    // Vite's dev server rejects unknown Host headers; list the public addresses it is reached by.
    allowedHosts: ['devine.my', '.trycloudflare.com'],
    // The browser calls /api on the page's own address and Vite forwards it to the backend on this PC.
    // One HTTPS address (for example a tunnel) is then enough: no mixed content, no CORS.
    proxy: {
      '/api': { target: 'http://127.0.0.1:8000', rewrite: path => path.replace(/^\/api/, '') },
    },
  },
})

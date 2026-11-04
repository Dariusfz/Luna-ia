import react from '@vitejs/plugin-react'
import { defineConfig } from 'vite'

// En desarrollo, /api se reenvía al backend Django (runserver en 127.0.0.1:8000).
// No se cambia el encabezado Host para que el origen (localhost:5173) coincida con CSRF.
export default defineConfig({
  plugins: [react()],
  server: {
    host: true,                      // escucha en la red, no solo en localhost
    port: 5173,
    allowedHosts: ['.ngrok-free.dev'], // acepta cualquier subdominio de ngrok
    proxy: {
      '/api': {
        target: 'http://127.0.0.1:8000',
      },
    },
  },
})
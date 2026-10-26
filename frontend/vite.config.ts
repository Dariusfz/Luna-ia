import react from '@vitejs/plugin-react'
import { defineConfig } from 'vite'

// En desarrollo, /api se reenvía al backend Django (runserver en 127.0.0.1:8000).
// No se cambia el encabezado Host para que el origen (localhost:5173) coincida con CSRF.
export default defineConfig({
  plugins: [react()],
  server: {
    port: 5173,
    proxy: {
      '/api': {
        target: 'http://127.0.0.1:8000',
      },
    },
  },
})

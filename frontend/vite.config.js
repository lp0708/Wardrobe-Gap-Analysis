import react from '@vitejs/plugin-react'
import { defineConfig } from 'vite'

// https://vite.dev/config/
export default defineConfig({
  plugins: [react()],
  server: {
    // Fail loudly if 5173 is taken instead of silently moving to 5174 - a
    // shifted port is what breaks CORS against the FastAPI backend.
    port: 5173,
    strictPort: true,
  },
})

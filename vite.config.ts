import { defineConfig } from 'vite'
import react from '@vitejs/plugin-react'
import tailwindcss from '@tailwindcss/vite'
import path from 'path'

export default defineConfig({
  plugins: [tailwindcss(), react()],
  root: 'src',
  build: {
    outDir: '../dist/renderer',
    emptyOutDir: true,
    rollupOptions: {
      input: {
        chat: path.resolve(__dirname, 'src/chat/index.html'),
        popup: path.resolve(__dirname, 'src/popup/index.html'),
      }
    }
  },
  server: {
    port: 5173
  }
})

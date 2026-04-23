import { defineConfig } from 'vite'
import react from '@vitejs/plugin-react'
import tailwindcss from '@tailwindcss/vite'
import path from 'path'

export default defineConfig({
  plugins: [tailwindcss(), react()],
  root: 'src',
  base: './',
  build: {
    outDir: '../dist/renderer',
    emptyOutDir: true,
    rollupOptions: {
      input: {
        chat: path.resolve(__dirname, 'src/chat/index.html'),
        popup: path.resolve(__dirname, 'src/popup/index.html'),
        setup: path.resolve(__dirname, 'src/setup/index.html'),
        overlay: path.resolve(__dirname, 'src/overlay/index.html'),
        'champ-select': path.resolve(__dirname, 'src/champ-select/index.html'),
      }
    }
  },
  server: {
    port: 5173
  }
})

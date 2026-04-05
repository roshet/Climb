import { contextBridge } from 'electron'

// Minimal preload — UI talks directly to FastAPI over HTTP
// Only expose the sidecar port so React knows where to connect
contextBridge.exposeInMainWorld('sidecar', {
  port: process.env.SIDECAR_PORT || '8765',
})

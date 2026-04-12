import { contextBridge, ipcRenderer } from 'electron'

contextBridge.exposeInMainWorld('sidecar', {
  port: process.env.SIDECAR_PORT || '8765',
})

contextBridge.exposeInMainWorld('electron', {
  setupComplete: (data: object) => ipcRenderer.send('setup-complete', data),
  getConfig: () => ipcRenderer.invoke('get-config'),
  onSetupError: (cb: (error: string) => void) => {
    ipcRenderer.on('setup-error', (_e, error: string) => cb(error))
  },
})

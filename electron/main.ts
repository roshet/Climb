import { app, BrowserWindow, Tray, Menu, nativeImage, screen } from 'electron'
import path from 'path'
import { spawn, ChildProcess } from 'child_process'

const SIDECAR_PORT = process.env.SIDECAR_PORT || '8765'
const SIDECAR_URL = `http://127.0.0.1:${SIDECAR_PORT}`
const isDev = !app.isPackaged

let tray: Tray | null = null
let chatWindow: BrowserWindow | null = null
let popupWindow: BrowserWindow | null = null
let sidecarProcess: ChildProcess | null = null
let statusPollInterval: ReturnType<typeof setInterval> | null = null

// --- Sidecar Management ---

function startSidecar() {
  const pythonPath = isDev
    ? path.join(__dirname, '..', '..', 'sidecar', 'venv', 'Scripts', 'python.exe')
    : path.join(process.resourcesPath, 'sidecar', 'venv', 'Scripts', 'python.exe')

  const sidecarDir = isDev
    ? path.join(__dirname, '..', '..', 'sidecar')
    : path.join(process.resourcesPath, 'sidecar')

  sidecarProcess = spawn(pythonPath, ['-m', 'uvicorn', 'main:app', '--port', SIDECAR_PORT], {
    cwd: sidecarDir,
    env: { ...process.env },
  })

  sidecarProcess.stdout?.on('data', (d: Buffer) => console.log('[sidecar]', d.toString().trim()))
  sidecarProcess.stderr?.on('data', (d: Buffer) => console.error('[sidecar]', d.toString().trim()))
}

function stopSidecar() {
  if (sidecarProcess) {
    sidecarProcess.kill()
    sidecarProcess = null
  }
}

// --- Window Management ---

function createChatWindow(matchId?: string) {
  if (chatWindow) {
    if (matchId) {
      const url = isDev
        ? `http://localhost:5173/chat/index.html?matchId=${matchId}`
        : `file://${path.join(__dirname, '../renderer/chat/index.html')}?matchId=${matchId}`
      chatWindow.loadURL(url)
    }
    chatWindow.focus()
    return
  }
  chatWindow = new BrowserWindow({
    width: 480,
    height: 700,
    webPreferences: {
      preload: path.join(__dirname, 'preload.js'),
      contextIsolation: true,
    },
    title: 'LoL Analyst',
    backgroundColor: '#1a1a2e',
  })
  const baseUrl = isDev ? 'http://localhost:5173' : `file://${path.join(__dirname, '../renderer')}`
  const suffix = matchId ? `?matchId=${matchId}` : ''
  chatWindow.loadURL(`${baseUrl}/chat/index.html${suffix}`)
  chatWindow.on('closed', () => { chatWindow = null })
}

function showPopup(matchId: string) {
  if (popupWindow) {
    popupWindow.close()
  }
  popupWindow = new BrowserWindow({
    width: 380,
    height: 520,
    frame: false,
    alwaysOnTop: true,
    resizable: false,
    webPreferences: {
      preload: path.join(__dirname, 'preload.js'),
      contextIsolation: true,
    },
    backgroundColor: '#1a1a2e',
  })

  const baseUrl = isDev ? 'http://localhost:5173' : `file://${path.join(__dirname, '../renderer')}`
  popupWindow.loadURL(`${baseUrl}/popup/index.html?matchId=${matchId}`)

  // Position bottom-right
  const { width, height } = screen.getPrimaryDisplay().workAreaSize
  popupWindow.setPosition(width - 400, height - 540)

  // Auto-dismiss after 60 seconds
  setTimeout(() => {
    if (popupWindow && !popupWindow.isDestroyed()) {
      popupWindow.close()
    }
  }, 60000)

  popupWindow.on('closed', () => { popupWindow = null })
}

// --- Status Polling ---

async function pollStatus() {
  try {
    const res = await fetch(`${SIDECAR_URL}/status`)
    if (!res.ok) return
    const data = await res.json() as { pending_popup: string | null; open_chat: string | null }
    if (data.pending_popup) {
      showPopup(data.pending_popup)
      await fetch(`${SIDECAR_URL}/status/clear`, { method: 'POST' })
    }
    if (data.open_chat !== null && data.open_chat !== undefined) {
      createChatWindow(data.open_chat || undefined)
    }
  } catch {
    // Sidecar not ready yet
  }
}

// --- Tray ---

function createTray() {
  const icon = nativeImage.createEmpty()
  tray = new Tray(icon)
  const menu = Menu.buildFromTemplate([
    { label: 'Open Chat', click: () => createChatWindow() },
    { type: 'separator' },
    { label: 'Quit', click: () => app.quit() },
  ])
  tray.setContextMenu(menu)
  tray.setToolTip('LoL Analyst')
  tray.on('click', () => createChatWindow())
}

// --- App Lifecycle ---

app.whenReady().then(() => {
  startSidecar()
  createTray()
  createChatWindow()

  // Wait 3s for sidecar to boot, then start polling
  setTimeout(() => {
    statusPollInterval = setInterval(pollStatus, 5000)
  }, 3000)
})

app.on('window-all-closed', (e: Event) => {
  e.preventDefault() // Keep running in tray
})

app.on('before-quit', () => {
  if (statusPollInterval) clearInterval(statusPollInterval)
  stopSidecar()
})

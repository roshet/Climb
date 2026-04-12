import { app, BrowserWindow, Tray, Menu, nativeImage, screen, ipcMain } from 'electron'
import path from 'path'
import { spawn, ChildProcess } from 'child_process'
import fs from 'fs'

app.setName('Climb')

const SIDECAR_PORT = process.env.SIDECAR_PORT || '8765'
const SIDECAR_URL = `http://127.0.0.1:${SIDECAR_PORT}`
const isDev = !app.isPackaged

let tray: Tray | null = null
let chatWindow: BrowserWindow | null = null
let popupWindow: BrowserWindow | null = null
let setupWindow: BrowserWindow | null = null
let sidecarProcess: ChildProcess | null = null
let statusPollInterval: ReturnType<typeof setInterval> | null = null

// --- Config ---

interface Config {
  riotApiKey: string
  geminiApiKey: string
  summonerName: string
  tagLine: string
  region: string
}

function getConfigPath(): string {
  return path.join(app.getPath('userData'), 'config.json')
}

function loadConfig(): Config | null {
  try {
    const data = fs.readFileSync(getConfigPath(), 'utf-8')
    return JSON.parse(data) as Config
  } catch {
    return null
  }
}

function saveConfig(config: Config): void {
  const dir = app.getPath('userData')
  if (!fs.existsSync(dir)) fs.mkdirSync(dir, { recursive: true })
  fs.writeFileSync(getConfigPath(), JSON.stringify(config, null, 2))
}

// --- Sidecar Management ---

function startSidecar(config: Config) {
  const pythonPath = isDev
    ? path.join(__dirname, '..', '..', 'sidecar', 'venv', 'Scripts', 'python.exe')
    : path.join(process.resourcesPath, 'sidecar', 'venv', 'Scripts', 'python.exe')

  const sidecarDir = isDev
    ? path.join(__dirname, '..', '..', 'sidecar')
    : path.join(process.resourcesPath, 'sidecar')

  sidecarProcess = spawn(pythonPath, ['-m', 'uvicorn', 'main:app', '--port', SIDECAR_PORT], {
    cwd: sidecarDir,
    env: {
      ...process.env,
      RIOT_API_KEY: config.riotApiKey,
      GEMINI_API_KEY: config.geminiApiKey,
    },
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

async function waitForSidecar(timeoutMs = 10000): Promise<boolean> {
  const start = Date.now()
  while (Date.now() - start < timeoutMs) {
    try {
      const res = await fetch(`${SIDECAR_URL}/status`)
      if (res.ok) return true
    } catch { /* not ready yet */ }
    await new Promise(r => setTimeout(r, 500))
  }
  return false
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
    title: 'Climb',
    backgroundColor: '#1a1a2e',
  })
  const baseUrl = isDev ? 'http://localhost:5173' : `file://${path.join(__dirname, '../renderer')}`
  const suffix = matchId ? `?matchId=${matchId}` : ''
  chatWindow.loadURL(`${baseUrl}/chat/index.html${suffix}`)
  chatWindow.on('closed', () => { chatWindow = null })
}

function createSetupWindow() {
  if (setupWindow) { setupWindow.focus(); return }
  setupWindow = new BrowserWindow({
    width: 420,
    height: 580,
    resizable: false,
    webPreferences: {
      preload: path.join(__dirname, 'preload.js'),
      contextIsolation: true,
    },
    title: 'Climb Setup',
    backgroundColor: '#1a1a2e',
  })
  const url = isDev
    ? 'http://localhost:5173/setup/index.html'
    : `file://${path.join(__dirname, '../renderer/setup/index.html')}`
  setupWindow.loadURL(url)
  setupWindow.on('closed', () => { setupWindow = null })
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

  const { width, height } = screen.getPrimaryDisplay().workAreaSize
  popupWindow.setPosition(width - 400, height - 540)

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

// --- IPC Handlers ---

ipcMain.handle('get-config', () => loadConfig())

ipcMain.on('setup-complete', async (_event, data: Config) => {
  saveConfig(data)
  stopSidecar()
  startSidecar(data)

  const ready = await waitForSidecar()
  if (!ready) {
    setupWindow?.webContents.send('setup-error', 'Sidecar failed to start. Check your API keys.')
    stopSidecar()
    return
  }

  try {
    const res = await fetch(`${SIDECAR_URL}/setup`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({
        summoner_name: data.summonerName,
        tag_line: data.tagLine,
        region: data.region,
      }),
    })
    if (!res.ok) {
      const err = await res.json() as { detail: string }
      setupWindow?.webContents.send('setup-error', err.detail || 'Summoner not found.')
      stopSidecar()
      return
    }
  } catch {
    setupWindow?.webContents.send('setup-error', 'Could not connect to sidecar.')
    stopSidecar()
    return
  }

  app.setLoginItemSettings({ openAtLogin: true })
  setupWindow?.close()
  createChatWindow()

  if (statusPollInterval) clearInterval(statusPollInterval)
  statusPollInterval = setInterval(pollStatus, 5000)
})

// --- Tray ---

function createTray() {
  const icon = nativeImage.createEmpty()
  tray = new Tray(icon)
  const menu = Menu.buildFromTemplate([
    { label: 'Open Chat', click: () => createChatWindow() },
    { label: 'Settings', click: () => createSetupWindow() },
    { type: 'separator' },
    { label: 'Quit', click: () => app.quit() },
  ])
  tray.setContextMenu(menu)
  tray.setToolTip('Climb')
  tray.on('click', () => createChatWindow())
}

// --- App Lifecycle ---

app.whenReady().then(() => {
  createTray()
  const config = loadConfig()
  if (!config) {
    createSetupWindow()
  } else {
    startSidecar(config)
    createChatWindow()
    setTimeout(() => {
      statusPollInterval = setInterval(pollStatus, 5000)
    }, 3000)
  }
})

app.on('window-all-closed', (e: Event) => {
  e.preventDefault()
})

app.on('before-quit', () => {
  if (statusPollInterval) clearInterval(statusPollInterval)
  stopSidecar()
})

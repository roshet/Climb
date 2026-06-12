import { app, BrowserWindow, Tray, Menu, nativeImage, screen, ipcMain } from 'electron'
import path from 'path'
import { spawn, execSync, ChildProcess } from 'child_process'
import fs from 'fs'

app.setName('Climb')

const isDev = !app.isPackaged

// Dev isolation: give the dev build its own userData (config + logs) and sidecar
// port so it never collides with an installed copy of Climb on the same machine.
// Must run before the app is ready and before the single-instance lock, since both
// key off the userData path. The env var is also read by preload.ts, so the
// renderer talks to the same port.
if (isDev) {
  app.setPath('userData', path.join(app.getPath('appData'), 'Climb-dev'))
  if (!process.env.SIDECAR_PORT) process.env.SIDECAR_PORT = '8766'
}

const SIDECAR_PORT = process.env.SIDECAR_PORT || '8765'
const SIDECAR_URL = `http://127.0.0.1:${SIDECAR_PORT}`

let tray: Tray | null = null
let chatWindow: BrowserWindow | null = null
let popupWindow: BrowserWindow | null = null
let setupWindow: BrowserWindow | null = null
let sidecarProcess: ChildProcess | null = null
let _restartTimer: ReturnType<typeof setTimeout> | null = null
let statusPollInterval: ReturnType<typeof setInterval> | null = null
let overlayWindow: BrowserWindow | null = null
let _wasInGame = false
let champSelectWindow: BrowserWindow | null = null
let _wasInChampSelect = false
let _lastConfig: Config | null = null
let _isQuitting = false
let _lastPopupMatchId: string | null = null

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

function configEqual(a: Config, b: Config): boolean {
  return a.riotApiKey === b.riotApiKey
    && a.geminiApiKey === b.geminiApiKey
    && a.summonerName === b.summonerName
    && a.tagLine === b.tagLine
    && a.region === b.region
}

// --- Logging ---
// Central logfile for the Electron main process: its own lifecycle events,
// captured sidecar stdout/stderr, and errors forwarded from renderer windows.
// The Python sidecar writes its own logs/sidecar.log alongside this file.

const LOG_DIR = path.join(app.getPath('userData'), 'logs')
const MAIN_LOG = path.join(LOG_DIR, 'main.log')
const LOG_MAX_BYTES = 1_000_000

function logToFile(line: string): void {
  try {
    if (!fs.existsSync(LOG_DIR)) fs.mkdirSync(LOG_DIR, { recursive: true })
    // Size-based rotation: keep one previous file (main.log.1).
    try {
      if (fs.statSync(MAIN_LOG).size > LOG_MAX_BYTES) {
        fs.renameSync(MAIN_LOG, `${MAIN_LOG}.1`)
      }
    } catch { /* no existing logfile yet */ }
    const ts = new Date().toISOString()
    fs.appendFileSync(MAIN_LOG, `${ts} ${line}\n`)
  } catch { /* never let logging crash the app */ }
}

function log(line: string): void {
  console.log(line)
  logToFile(line)
}

// --- Sidecar Management ---

function killPortProcess(port: string) {
  try {
    const output = execSync(`netstat -ano | findstr :${port}`, { encoding: 'utf8' })
    for (const line of output.trim().split('\n')) {
      if (!line.includes('LISTENING')) continue
      const parts = line.trim().split(/\s+/)
      const pid = parts[parts.length - 1]
      if (pid && pid !== '0') {
        try { execSync(`taskkill /F /PID ${pid}`) } catch { /* already gone */ }
      }
    }
  } catch { /* no process on port */ }
}

function startSidecar(config: Config) {
  _lastConfig = config
  // Any pending crash-restart is superseded by this start: cancel it so restart
  // timers can't accumulate and race two uvicorns onto the same port.
  if (_restartTimer) { clearTimeout(_restartTimer); _restartTimer = null }
  // Detach the previous process's restart listener before killPortProcess()
  // force-kills it below — otherwise its 'close' fires and schedules a phantom
  // restart that collides on the port with the sidecar we're about to start.
  if (sidecarProcess) { sidecarProcess.removeAllListeners('close'); sidecarProcess = null }
  killPortProcess(SIDECAR_PORT)
  const pythonPath = isDev
    ? path.join(__dirname, '..', '..', 'sidecar', 'venv', 'Scripts', 'python.exe')
    : path.join(process.resourcesPath, 'sidecar', 'venv', 'Scripts', 'python.exe')

  const sidecarDir = isDev
    ? path.join(__dirname, '..', '..', 'sidecar')
    : path.join(process.resourcesPath, 'sidecar')

  const dbPath = isDev
    ? path.join(__dirname, '..', '..', 'sidecar', 'analyst.db')
    : path.join(app.getPath('userData'), 'analyst.db')

  sidecarProcess = spawn(pythonPath, ['-m', 'uvicorn', 'main:app', '--port', SIDECAR_PORT], {
    cwd: sidecarDir,
    env: {
      ...process.env,
      RIOT_API_KEY: config.riotApiKey,
      GEMINI_API_KEY: config.geminiApiKey,
      REGION: config.region,
      DB_PATH: dbPath,
      LOG_DIR: app.getPath('userData'),
    },
  })

  sidecarProcess.stdout?.on('data', (d: Buffer) => log(`[sidecar] ${d.toString().trim()}`))
  sidecarProcess.stderr?.on('data', (d: Buffer) => log(`[sidecar] ${d.toString().trim()}`))
  sidecarProcess.on('close', (code) => {
    if (!_isQuitting && _lastConfig) {
      log(`[sidecar] exited with code ${code}, restarting in 3s...`)
      _restartTimer = setTimeout(() => startSidecar(_lastConfig!), 3000)
    }
  })
}

function stopSidecar() {
  // Cancel any pending crash-restart: this is an intentional stop.
  if (_restartTimer) { clearTimeout(_restartTimer); _restartTimer = null }
  if (sidecarProcess) {
    // Detach the crash-restart handler first: the dying process must NOT
    // schedule a 3s auto-restart that would collide on the port with the
    // sidecar we're about to (re)start.
    sidecarProcess.removeAllListeners('close')
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
  const isSettings = loadConfig() !== null
  setupWindow = new BrowserWindow({
    width: 420,
    height: 580,
    resizable: false,
    webPreferences: {
      preload: path.join(__dirname, 'preload.js'),
      contextIsolation: true,
    },
    title: isSettings ? 'Settings' : 'Climb Setup',
    backgroundColor: '#1a1a2e',
  })
  // The window's static HTML <title> would otherwise override the title set
  // above; keep our mode-aware title (Settings vs Climb Setup) instead.
  setupWindow.on('page-title-updated', (e) => e.preventDefault())
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

function createOverlayWindow() {
  if (overlayWindow) return
  const { width } = screen.getPrimaryDisplay().workAreaSize
  overlayWindow = new BrowserWindow({
    width: 340,
    height: 400,
    x: width - 360,
    y: 20,
    transparent: true,
    frame: false,
    alwaysOnTop: true,
    focusable: false,
    skipTaskbar: true,
    webPreferences: {
      preload: path.join(__dirname, 'preload.js'),
      contextIsolation: true,
    },
  })
  overlayWindow.setAlwaysOnTop(true, 'screen-saver')
  const url = isDev
    ? 'http://localhost:5173/overlay/index.html'
    : `file://${path.join(__dirname, '../renderer/overlay/index.html')}`
  overlayWindow.loadURL(url)
  overlayWindow.on('closed', () => { overlayWindow = null })
}

function destroyOverlayWindow() {
  if (overlayWindow && !overlayWindow.isDestroyed()) {
    overlayWindow.close()
  }
  overlayWindow = null
}

function createChampSelectWindow() {
  if (champSelectWindow) return
  const { width } = screen.getPrimaryDisplay().workAreaSize
  champSelectWindow = new BrowserWindow({
    width: 320,
    height: 260,
    x: width - 340,
    y: 20,
    transparent: true,
    frame: false,
    alwaysOnTop: true,
    focusable: false,
    skipTaskbar: true,
    resizable: false,
    webPreferences: {
      preload: path.join(__dirname, 'preload.js'),
      contextIsolation: true,
    },
  })
  champSelectWindow.setAlwaysOnTop(true, 'screen-saver')
  const url = isDev
    ? 'http://localhost:5173/champ-select/index.html'
    : `file://${path.join(__dirname, '../renderer/champ-select/index.html')}`
  champSelectWindow.loadURL(url)
  champSelectWindow.on('closed', () => { champSelectWindow = null })
}

function destroyChampSelectWindow() {
  if (champSelectWindow && !champSelectWindow.isDestroyed()) {
    champSelectWindow.close()
  }
  champSelectWindow = null
}

// --- Status Polling ---

async function pollStatus() {
  try {
    const statusRes = await fetch(`${SIDECAR_URL}/status`)
    if (statusRes.ok) {
      const data = await statusRes.json() as { pending_popup: string | null; open_chat: string | null }
      if (data.pending_popup) {
        _lastPopupMatchId = data.pending_popup
        showPopup(data.pending_popup)
        await fetch(`${SIDECAR_URL}/status/clear`, { method: 'POST' })
        updateTrayMenu()
      }
      if (data.open_chat !== null && data.open_chat !== undefined) {
        createChatWindow(data.open_chat || undefined)
      }
    }
  } catch { /* sidecar not ready */ }

  try {
    const liveRes = await fetch(`${SIDECAR_URL}/live`)
    if (liveRes.ok) {
      const liveData = await liveRes.json() as { in_game: boolean }
      if (typeof liveData.in_game === 'boolean') {
        if (liveData.in_game && !_wasInGame) {
          createOverlayWindow()
        } else if (!liveData.in_game && _wasInGame) {
          destroyOverlayWindow()
        }
        _wasInGame = liveData.in_game
      }
    }
  } catch { /* sidecar not ready */ }

  try {
    const csRes = await fetch(`${SIDECAR_URL}/champ-select`)
    if (csRes.ok) {
      const csData = await csRes.json() as { in_champ_select: boolean }
      if (typeof csData.in_champ_select === 'boolean') {
        if (csData.in_champ_select && !_wasInChampSelect) {
          createChampSelectWindow()
        } else if (!csData.in_champ_select && _wasInChampSelect) {
          destroyChampSelectWindow()
        }
        _wasInChampSelect = csData.in_champ_select
      }
    }
  } catch { /* sidecar not ready */ }
}

// --- IPC Handlers ---

ipcMain.handle('get-config', () => loadConfig())

ipcMain.on('log-message', (_event, level: string, message: string) => {
  logToFile(`[renderer:${level}] ${message}`)
})

ipcMain.on('setup-complete', async (_event, data: Config) => {
  const existing = loadConfig()
  const firstRun = existing === null

  // Settings save with no actual changes: confirm without restarting the
  // sidecar, so opening Settings and hitting Save never interrupts a live game.
  if (!firstRun && existing && configEqual(existing, data)) {
    setupWindow?.webContents.send('setup-saved')
    return
  }

  // Validate the new config against a sidecar running with the new keys, but
  // don't persist it (or tear down a working analyst) until validation passes.
  stopSidecar()
  startSidecar(data)

  let errorMsg: string | null = null
  if (!(await waitForSidecar())) {
    errorMsg = 'Sidecar failed to start. Check your API keys.'
  } else {
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
        errorMsg = err.detail || 'Summoner not found.'
      }
    } catch {
      errorMsg = 'Could not connect to sidecar.'
    }
  }

  if (errorMsg) {
    setupWindow?.webContents.send('setup-error', errorMsg)
    // Roll back to the previously-working analyst, if there was one.
    stopSidecar()
    if (existing) startSidecar(existing)
    return
  }

  saveConfig(data)
  app.setLoginItemSettings({ openAtLogin: true })

  if (firstRun) {
    setupWindow?.close()
    createChatWindow()

    if (statusPollInterval) clearInterval(statusPollInterval)
    _wasInGame = false
    statusPollInterval = setInterval(pollStatus, 5000)
  } else {
    // Settings save: confirm in place instead of forcing focus into chat.
    setupWindow?.webContents.send('setup-saved')
  }
})

// --- Tray ---

function updateTrayMenu() {
  if (!tray) return
  const items: Electron.MenuItemConstructorOptions[] = [
    { label: 'Open Chat', click: () => createChatWindow() },
  ]
  if (_lastPopupMatchId) {
    items.push({ label: 'Last game', click: () => showPopup(_lastPopupMatchId!) })
  }
  items.push(
    { label: 'Settings', click: () => createSetupWindow() },
    { type: 'separator' },
    { label: 'Quit', click: () => app.quit() },
  )
  tray.setContextMenu(Menu.buildFromTemplate(items))
}

function createTray() {
  const iconPath = isDev
    ? path.join(__dirname, '..', '..', 'assets', 'icon.png')
    : path.join(process.resourcesPath, 'assets', 'icon.png')
  const icon = fs.existsSync(iconPath) ? nativeImage.createFromPath(iconPath) : nativeImage.createEmpty()
  tray = new Tray(icon)
  tray.setToolTip('Climb')
  tray.on('click', () => createChatWindow())
  updateTrayMenu()
}

// --- App Lifecycle ---

// Refuse to start a second copy of Climb: two instances would fight over the
// sidecar port (each startSidecar() force-kills whatever holds it, so they'd
// kill each other's sidecar in a loop). The dev build uses a separate userData
// path (above), giving it its own lock domain, so it can still run alongside an
// installed copy.
if (!app.requestSingleInstanceLock()) {
  app.quit()
} else {
  app.on('second-instance', () => {
    // Another launch was attempted; surface the existing window instead.
    const win = chatWindow ?? setupWindow
    if (win) {
      if (win.isMinimized()) win.restore()
      win.focus()
    } else {
      createChatWindow()
    }
  })

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
}

app.on('window-all-closed', (e: Event) => {
  e.preventDefault()
})

app.on('before-quit', () => {
  _isQuitting = true
  if (statusPollInterval) clearInterval(statusPollInterval)
  _wasInGame = false
  _wasInChampSelect = false
  destroyOverlayWindow()
  destroyChampSelectWindow()
  stopSidecar()
})

# Climb Packaging Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Package Climb as a Windows NSIS installer with bundled Python sidecar, first-run setup screen for API keys, and auto-start on login.

**Architecture:** `electron-builder` bundles `sidecar/` (including venv) as extraResources. `electron/main.ts` reads `%APPDATA%/Climb/config.json` on startup — opens a setup window if missing, otherwise starts the sidecar with injected API keys. A new `src/setup/` React page handles first-run and Settings updates via Electron IPC.

**Tech Stack:** Electron 28, React 18 + TypeScript, Tailwind CSS, electron-builder 26, NSIS

---

## File Map

| File | Action | Responsibility |
|---|---|---|
| `package.json` | **MODIFY** | Add `build` config for electron-builder (NSIS, extraResources) |
| `electron/main.ts` | **MODIFY** | Config load/save, sidecar env injection, setup window, IPC handlers, tray Settings, auto-start |
| `electron/preload.ts` | **MODIFY** | Expose IPC bridge (`setupComplete`, `getConfig`, `onSetupError`) |
| `src/setup/index.html` | **CREATE** | Entry HTML for setup page |
| `src/setup/App.tsx` | **CREATE** | First-run setup form (API keys + Riot ID) |
| `vite.config.ts` | **MODIFY** | Add setup as third rollup entry point |

---

## Task 1: Add electron-builder config to `package.json`

**Files:**
- Modify: `package.json`

- [ ] **Step 1: Add the `build` key to `package.json`**

Replace the entire `package.json` with:

```json
{
  "name": "lol-analyst",
  "version": "0.1.0",
  "main": "dist/electron/main.js",
  "scripts": {
    "dev": "tsc -p tsconfig.electron.json && concurrently \"vite\" \"tsc -p tsconfig.electron.json --watch\" \"electron .\"",
    "build": "vite build && tsc -p tsconfig.electron.json",
    "package": "npm run build && electron-builder"
  },
  "dependencies": {
    "react": "^18.3.1",
    "react-dom": "^18.3.1"
  },
  "devDependencies": {
    "@tailwindcss/vite": "^4.2.2",
    "@types/node": "^25.5.2",
    "@types/react": "^18.3.28",
    "@types/react-dom": "^18.3.7",
    "@vitejs/plugin-react": "^6.0.1",
    "autoprefixer": "^10.4.27",
    "concurrently": "^9.2.1",
    "electron": "^28.3.3",
    "electron-builder": "^26.8.1",
    "postcss": "^8.5.8",
    "tailwindcss": "^4.2.2",
    "typescript": "^6.0.2",
    "vite": "^8.0.3"
  },
  "build": {
    "appId": "com.climb.app",
    "productName": "Climb",
    "directories": {
      "output": "dist-installer"
    },
    "extraResources": [
      {
        "from": "sidecar",
        "to": "sidecar",
        "filter": ["**/*", "!analyst.db", "!.env", "!**/__pycache__/**", "!tests/**", "!*.pyc"]
      }
    ],
    "win": {
      "target": "nsis"
    },
    "nsis": {
      "oneClick": false,
      "allowToChangeInstallationDirectory": false,
      "createStartMenuShortcut": true
    }
  }
}
```

- [ ] **Step 2: Verify electron-builder can read the config**

```bash
cd "c:/Users/rohan/OneDrive/Desktop/NewProject" && npx electron-builder --help 2>&1 | head -5
```

Expected: electron-builder help text (confirms it's installed and readable)

- [ ] **Step 3: Commit**

```bash
git add package.json
git commit -m "feat: add electron-builder config for Climb NSIS installer"
```

---

## Task 2: Config management + sidecar env injection in `electron/main.ts`

**Files:**
- Modify: `electron/main.ts`

This task adds config load/save helpers, a `waitForSidecar` utility, and modifies `startSidecar` to accept a config and inject API keys as env vars. It does NOT yet wire up the IPC handlers or setup window — that's Task 5.

- [ ] **Step 1: Replace the entire contents of `electron/main.ts`**

```typescript
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
```

- [ ] **Step 2: TypeScript check**

```bash
cd "c:/Users/rohan/OneDrive/Desktop/NewProject" && npx tsc -p tsconfig.electron.json --noEmit 2>&1
```

Expected: zero errors

- [ ] **Step 3: Commit**

```bash
git add electron/main.ts
git commit -m "feat: config management, sidecar env injection, setup window, IPC handlers"
```

---

## Task 3: Update `electron/preload.ts` with IPC bridge

**Files:**
- Modify: `electron/preload.ts`

The setup page needs to send data to the main process (`setup-complete`) and receive errors back (`setup-error`). It also needs to read existing config to pre-fill the Settings form (`get-config`).

- [ ] **Step 1: Replace the entire contents of `electron/preload.ts`**

```typescript
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
```

- [ ] **Step 2: TypeScript check**

```bash
cd "c:/Users/rohan/OneDrive/Desktop/NewProject" && npx tsc -p tsconfig.electron.json --noEmit 2>&1
```

Expected: zero errors

- [ ] **Step 3: Commit**

```bash
git add electron/preload.ts
git commit -m "feat: expose IPC bridge in preload for setup window"
```

---

## Task 4: Create the setup page

**Files:**
- Create: `src/setup/index.html`
- Create: `src/setup/App.tsx`
- Modify: `vite.config.ts`

- [ ] **Step 1: Create `src/setup/index.html`**

```html
<!DOCTYPE html>
<html lang="en">
<head><meta charset="UTF-8"><title>Climb Setup</title></head>
<body>
  <div id="root"></div>
  <script type="module" src="./App.tsx"></script>
</body>
</html>
```

- [ ] **Step 2: Create `src/setup/App.tsx`**

```tsx
import { useState, useEffect } from 'react'
import { createRoot } from 'react-dom/client'
import '../index.css'

declare global {
  interface Window {
    sidecar: { port: string }
    electron: {
      setupComplete: (data: SetupData) => void
      getConfig: () => Promise<SetupData | null>
      onSetupError: (cb: (error: string) => void) => void
    }
  }
}

interface SetupData {
  riotApiKey: string
  geminiApiKey: string
  summonerName: string
  tagLine: string
  region: string
}

const REGIONS = ['NA1', 'EUW1', 'EUN1', 'KR', 'BR1', 'LA1', 'LA2', 'OC1', 'TR1', 'JP1']

function SetupApp() {
  const [riotApiKey, setRiotApiKey] = useState('')
  const [geminiApiKey, setGeminiApiKey] = useState('')
  const [summonerName, setSummonerName] = useState('')
  const [tagLine, setTagLine] = useState('')
  const [region, setRegion] = useState('NA1')
  const [loading, setLoading] = useState(false)
  const [error, setError] = useState('')

  useEffect(() => {
    window.electron.getConfig().then(config => {
      if (!config) return
      setRiotApiKey(config.riotApiKey)
      setGeminiApiKey(config.geminiApiKey)
      setSummonerName(config.summonerName)
      setTagLine(config.tagLine)
      setRegion(config.region)
    })
    window.electron.onSetupError(err => {
      setError(err)
      setLoading(false)
    })
  }, [])

  const submit = () => {
    if (!riotApiKey.trim() || !geminiApiKey.trim() || !summonerName.trim() || !tagLine.trim()) return
    setLoading(true)
    setError('')
    window.electron.setupComplete({
      riotApiKey: riotApiKey.trim(),
      geminiApiKey: geminiApiKey.trim(),
      summonerName: summonerName.trim(),
      tagLine: tagLine.trim(),
      region,
    })
  }

  const canSubmit = !loading && riotApiKey.trim() && geminiApiKey.trim() && summonerName.trim() && tagLine.trim()

  return (
    <div className="bg-[#1a1a2e] min-h-screen flex flex-col items-center justify-center text-white font-sans px-8">
      <h1 className="text-xl font-bold mb-1">Climb Setup</h1>
      <p className="text-gray-400 text-sm mb-6 text-center">Enter your API keys and Riot ID to get started.</p>

      <div className="w-full max-w-sm space-y-4">
        <div>
          <label className="text-gray-500 text-[10px] uppercase tracking-wide mb-1 block">Riot API Key</label>
          <input
            className="w-full bg-white/10 text-white text-sm rounded-xl px-3 py-2 outline-none placeholder-gray-500"
            placeholder="RGAPI-..."
            value={riotApiKey}
            onChange={e => setRiotApiKey(e.target.value)}
          />
        </div>

        <div>
          <label className="text-gray-500 text-[10px] uppercase tracking-wide mb-1 block">Gemini API Key</label>
          <input
            className="w-full bg-white/10 text-white text-sm rounded-xl px-3 py-2 outline-none placeholder-gray-500"
            placeholder="AIza..."
            value={geminiApiKey}
            onChange={e => setGeminiApiKey(e.target.value)}
          />
        </div>

        <div>
          <label className="text-gray-500 text-[10px] uppercase tracking-wide mb-1 block">Riot ID</label>
          <div className="flex gap-2">
            <input
              className="flex-1 bg-white/10 text-white text-sm rounded-xl px-3 py-2 outline-none placeholder-gray-500"
              placeholder="Game Name"
              value={summonerName}
              onChange={e => setSummonerName(e.target.value)}
            />
            <span className="text-gray-500 self-center">#</span>
            <input
              className="w-20 bg-white/10 text-white text-sm rounded-xl px-3 py-2 outline-none placeholder-gray-500"
              placeholder="TAG"
              value={tagLine}
              onChange={e => setTagLine(e.target.value)}
            />
          </div>
        </div>

        <select
          className="w-full bg-white/10 text-white text-sm rounded-xl px-3 py-2 outline-none"
          value={region}
          onChange={e => setRegion(e.target.value)}
        >
          {REGIONS.map(r => <option key={r} value={r}>{r}</option>)}
        </select>

        {error && <p className="text-red-400 text-xs">{error}</p>}

        <button
          onClick={submit}
          disabled={!canSubmit}
          className="w-full py-2 bg-blue-600 hover:bg-blue-700 disabled:opacity-40 text-white text-sm rounded-xl transition-colors"
        >
          {loading ? 'Connecting...' : 'Get Started'}
        </button>
      </div>
    </div>
  )
}

createRoot(document.getElementById('root')!).render(<SetupApp />)
```

- [ ] **Step 3: Add setup entry to `vite.config.ts`**

Replace the entire file:

```typescript
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
        setup: path.resolve(__dirname, 'src/setup/index.html'),
      }
    }
  },
  server: {
    port: 5173
  }
})
```

- [ ] **Step 4: TypeScript + build check**

```bash
cd "c:/Users/rohan/OneDrive/Desktop/NewProject" && npx tsc --noEmit 2>&1 && npm run build 2>&1 | tail -10
```

Expected: zero TS errors, build succeeds and shows `setup-*.js` in the output

- [ ] **Step 5: Commit**

```bash
git add src/setup/index.html src/setup/App.tsx vite.config.ts
git commit -m "feat: setup page for first-run API key and Riot ID configuration"
```

---

## Task 5: Final verification

**Files:** None (verification only)

- [ ] **Step 1: Full TypeScript check (renderer + electron)**

```bash
cd "c:/Users/rohan/OneDrive/Desktop/NewProject" && npx tsc --noEmit 2>&1 && npx tsc -p tsconfig.electron.json --noEmit 2>&1
```

Expected: zero errors from both

- [ ] **Step 2: Full build**

```bash
cd "c:/Users/rohan/OneDrive/Desktop/NewProject" && npm run build 2>&1 | tail -15
```

Expected: clean build, output includes `setup/index.html` and `setup-*.js`

- [ ] **Step 3: Smoke test in dev mode**

```bash
cd "c:/Users/rohan/OneDrive/Desktop/NewProject" && npm run dev
```

Verify:
- If `%APPDATA%/Climb/config.json` does not exist: setup window opens on launch
- If it does exist (from previous runs): chat window opens directly
- Tray menu has "Settings" item that opens the setup window pre-filled

To force first-run: temporarily rename or delete `%APPDATA%/Climb/config.json`.

- [ ] **Step 4: Commit and git log check**

```bash
git log --oneline -8
```

Expected: clean trail with commits from all 4 tasks

---

## Notes for the packager build

The `npm run package` command will produce `dist-installer/Climb Setup.exe`. This requires the full `sidecar/venv/` to be present locally (~150-200MB installer). The build will take several minutes on first run while electron-builder downloads build tools (NSIS). This is expected.

Do NOT run `npm run package` as part of the automated tasks above — it requires the full venv and is a manual verification step.

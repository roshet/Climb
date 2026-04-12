# Climb — Packaging & Installer Design Spec

**Date:** 2026-04-12
**Status:** Approved

---

## Goal

Package the Climb app as a Windows NSIS installer (`Climb Setup.exe`) that bundles the Python sidecar, starts automatically on Windows login, and includes a first-run setup screen and in-app Settings for updating API keys.

---

## App Identity

| Field | Value |
|---|---|
| App name | Climb |
| App ID | `com.climb.app` |
| Installer output | `dist-installer/Climb Setup.exe` |
| Install location | `%LOCALAPPDATA%\Programs\Climb` |
| Config file | `%APPDATA%\Climb\config.json` |

---

## Architecture

### Sidecar Bundling

`electron-builder` bundles the entire `sidecar/` directory (including `venv/`) as `extraResources`. At runtime in production, `process.resourcesPath/sidecar/` is where it lands. `electron/main.ts` already uses this path via `process.resourcesPath` when `app.isPackaged` is true.

**Excluded from bundle:**
- `sidecar/analyst.db` — created fresh on first run
- `sidecar/.env` — replaced by `%APPDATA%/Climb/config.json`
- `sidecar/__pycache__/`, `sidecar/tests/`

### Config File

Stored at `%APPDATA%/Climb/config.json`:

```json
{
  "riot_api_key": "RGAPI-...",
  "gemini_api_key": "...",
  "summoner_name": "...",
  "tag_line": "NA1",
  "region": "NA1"
}
```

On every launch, Electron reads this file and passes `RIOT_API_KEY` and `GEMINI_API_KEY` as environment variables when spawning the sidecar process. No changes needed to Python code.

### First-Run Detection

If `%APPDATA%/Climb/config.json` does not exist, Electron opens the setup window instead of the chat window on startup.

### Auto-Start

On first successful setup completion, `app.setLoginItemSettings({ openAtLogin: true })` is called once to register Climb with Windows startup.

---

## Components

### `electron/main.ts` (modify)

- Add `loadConfig()` — reads `%APPDATA%/Climb/config.json`, returns parsed object or `null`
- Add `saveConfig(config)` — writes config to `%APPDATA%/Climb/config.json`
- Modify `startSidecar()` — inject `RIOT_API_KEY` and `GEMINI_API_KEY` from config into sidecar env
- Add `createSetupWindow()` — opens setup page; closes itself after successful submit
- Modify `app.whenReady()` — open setup window if no config, else open chat window
- Add **Settings** item to tray menu — reopens setup window (pre-filled)
- Call `app.setLoginItemSettings({ openAtLogin: true })` after first successful setup

### `src/setup/index.tsx` (create)

React page with a form collecting:
- Riot API Key (text input)
- Gemini API Key (text input)
- Summoner Name (text input)
- Tag Line (text input, e.g. `NA1`)
- Region (dropdown: NA1, EUW1, EUN1, KR, BR1, LA1, LA2, OC1, TR1, JP1)

On submit:
1. Send `ipcRenderer.send('setup-complete', formData)` to main process
2. Main process saves config to disk
3. Main process starts sidecar (now has API keys to inject)
4. Main process waits up to 10 seconds for sidecar to respond on `/status`
5. Main process POSTs to `/setup` endpoint with summoner details
6. On success: call `app.setLoginItemSettings`, close setup window, open chat window
7. On failure (bad key or summoner not found): send error back to renderer, show inline error, stop sidecar

Pre-fills fields from existing config if opened via Settings tray menu item.

### `src/setup/index.html` (create)

Entry HTML for the setup page — same pattern as `src/popup/index.html` and `src/chat/index.html`.

### `vite.config.ts` (modify)

Add `setup` as a third rollup input entry point alongside `popup` and `chat`.

### `package.json` (modify)

Add `"build"` config for electron-builder:

```json
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
      "filter": ["**/*", "!analyst.db", "!.env", "!__pycache__/**", "!tests/**"]
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
```

---

## Setup Window Behaviour

| State | Behaviour |
|---|---|
| First launch, no config | Setup window opens automatically |
| Setup submitted successfully | Config saved, auto-start registered, setup closes, chat opens |
| Setup submit fails (bad API key / network) | Show inline error, stay on setup screen |
| Tray → Settings | Setup window opens pre-filled with current config values |
| Settings updated | Config overwritten, sidecar killed and restarted with new env vars, `/setup` called again with new summoner details |

---

## Build Command

```bash
npm run package
```

This runs `npm run build && electron-builder`, producing `dist-installer/Climb Setup.exe`.

---

## Out of Scope

- Auto-updater (no update server configured)
- macOS / Linux builds
- Code signing (requires paid certificate — skip for personal use)
- Riot API key auto-refresh (user pastes new key via Settings daily)

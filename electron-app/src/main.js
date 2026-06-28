/**
 * Bunshin Desktop — Electron main process.
 *
 * Responsibilities:
 *   1. Spawn the `bunshin web` server as a child process on app launch.
 *   2. Wait until the server is reachable, then show the main window.
 *   3. Build localized native menus (auto-following OS language).
 *   4. Register global keyboard shortcuts (⌘+K, ⌘+N, ⌘+R, etc.).
 *   5. Forward system notifications when bunshin emits Insights.
 *   6. Cleanly terminate the server on quit (no orphan processes).
 *   7. Persist window geometry between sessions.
 */

const { app, BrowserWindow, Menu, Tray, nativeImage, shell, dialog, ipcMain, globalShortcut, nativeTheme, Notification } = require('electron');
const path = require('node:path');
const fs = require('node:fs');
const os = require('node:os');
const net = require('node:net');
const { spawn } = require('node:child_process');
const Store = require('electron-store');

// Auto-updater (production builds only — silently no-ops in dev)
let autoUpdater = null;
try {
  autoUpdater = require('electron-updater').autoUpdater;
} catch {
  // not installed yet, will be on next npm install
}

// ────────────────────────────────────────────────────────────
// Config
// ────────────────────────────────────────────────────────────
const SERVER_HOST = '127.0.0.1';
const SERVER_PORT = 8000;
const SERVER_URL = `http://${SERVER_HOST}:${SERVER_PORT}`;
const SERVER_READY_TIMEOUT_MS = 30_000;

const store = new Store({
  defaults: {
    window: { width: 1280, height: 860, x: undefined, y: undefined },
    notifications: true,
  },
});

let mainWindow = null;
let tray = null;
let splashWindow = null;
let serverProcess = null;
let serverStartedByUs = false;
let menuLanguage = 'en';

// ────────────────────────────────────────────────────────────
// i18n
// ────────────────────────────────────────────────────────────
function detectLocale() {
  // Prefer the app locale (set after `app.whenReady()`).
  // Fall back to OS env vars so this also works at module load time.
  let raw =
    (typeof app.getLocale === 'function' && app.isReady() ? app.getLocale() : '') ||
    process.env.LANG ||
    process.env.LC_ALL ||
    process.env.LC_MESSAGES ||
    'en';
  return raw.toLowerCase().startsWith('ja') ? 'ja' : 'en';
}

function loadLocale() {
  const lang = detectLocale();
  menuLanguage = lang;
  const localePath = path.join(__dirname, '..', 'i18n', `${lang}.json`);
  try {
    return JSON.parse(fs.readFileSync(localePath, 'utf8'));
  } catch {
    return JSON.parse(fs.readFileSync(path.join(__dirname, '..', 'i18n', 'en.json'), 'utf8'));
  }
}

// Initial best-effort load (uses env vars). Will be refreshed once app is ready.
let t = loadLocale();

// ────────────────────────────────────────────────────────────
// Server lifecycle
// ────────────────────────────────────────────────────────────
function findBunshinBinary() {
  // 1. Production: bundled inside Contents/Resources/bunshin/ via electron-
  //    builder's extraResources. This is what ships in the DMG so the app
  //    works on a clean Mac with no Python install.
  // 2. Dev fallback: a venv install at ~/.bunshin/venv/bin or a brew bin.
  const bundled = process.resourcesPath
    ? path.join(process.resourcesPath, 'bunshin', 'bunshin')
    : null;
  const candidates = [
    bundled,
    path.join(os.homedir(), '.bunshin', 'venv', 'bin', 'bunshin'),
    '/usr/local/bin/bunshin',
    '/opt/homebrew/bin/bunshin',
  ].filter(Boolean);
  for (const p of candidates) {
    if (fs.existsSync(p)) return p;
  }
  return null;
}

function checkPortInUse(host, port, timeoutMs = 500) {
  return new Promise((resolve) => {
    const socket = new net.Socket();
    let resolved = false;
    const done = (inUse) => {
      if (resolved) return;
      resolved = true;
      socket.destroy();
      resolve(inUse);
    };
    socket.setTimeout(timeoutMs);
    socket.once('connect', () => done(true));
    socket.once('timeout', () => done(false));
    socket.once('error', () => done(false));
    socket.connect(port, host);
  });
}

async function waitForServer(maxMs = SERVER_READY_TIMEOUT_MS) {
  const start = Date.now();
  while (Date.now() - start < maxMs) {
    if (await checkPortInUse(SERVER_HOST, SERVER_PORT)) return true;
    await new Promise((r) => setTimeout(r, 300));
  }
  return false;
}

async function startServer() {
  const alreadyRunning = await checkPortInUse(SERVER_HOST, SERVER_PORT);
  if (alreadyRunning) {
    console.log('[bunshin] server already running, attaching to existing');
    serverStartedByUs = false;
    return true;
  }

  const bin = findBunshinBinary();
  if (!bin) {
    dialog.showErrorBox(
      t.dialog.bunshinNotFoundTitle,
      t.dialog.bunshinNotFoundBody.replace('{path}', '~/.bunshin/venv/bin/bunshin')
    );
    return false;
  }

  console.log('[bunshin] spawning:', bin, 'web');
  serverProcess = spawn(bin, ['web'], {
    detached: false,
    stdio: ['ignore', 'pipe', 'pipe'],
    env: { ...process.env },
  });
  serverStartedByUs = true;

  serverProcess.stdout?.on('data', (d) => console.log('[bunshin/server]', d.toString().trim()));
  serverProcess.stderr?.on('data', (d) => console.error('[bunshin/server]', d.toString().trim()));
  serverProcess.on('exit', (code, signal) => {
    console.log('[bunshin] server exited', { code, signal });
    serverProcess = null;
  });

  const ready = await waitForServer();
  if (!ready) {
    dialog.showErrorBox(
      t.dialog.serverTimeoutTitle,
      t.dialog.serverTimeoutBody
    );
    return false;
  }
  return true;
}

function stopServer() {
  if (!serverStartedByUs || !serverProcess) return;
  try {
    serverProcess.kill('SIGTERM');
    setTimeout(() => {
      if (serverProcess && !serverProcess.killed) {
        serverProcess.kill('SIGKILL');
      }
    }, 2_000);
  } catch (e) {
    console.error('[bunshin] failed to kill server', e);
  }
}

// ────────────────────────────────────────────────────────────
// Splash window — shown while the bunshin web server is starting up.
// ────────────────────────────────────────────────────────────
function createSplash() {
  splashWindow = new BrowserWindow({
    width: 480,
    height: 320,
    frame: false,
    transparent: true,
    backgroundColor: '#00000000',
    alwaysOnTop: true,
    resizable: false,
    movable: true,
    skipTaskbar: false,
    show: false,
    hasShadow: true,
    webPreferences: {
      contextIsolation: true,
      nodeIntegration: false,
    },
  });
  splashWindow.loadFile(path.join(__dirname, 'splash.html'));
  splashWindow.once('ready-to-show', () => splashWindow.show());
}

function setSplashStatus(msg) {
  if (!splashWindow || splashWindow.isDestroyed()) return;
  splashWindow.webContents.executeJavaScript(
    `(() => { const el = document.getElementById('status'); if (el) el.textContent = ${JSON.stringify(msg)}; })();`
  ).catch(() => {});
}

function closeSplash() {
  if (splashWindow && !splashWindow.isDestroyed()) {
    splashWindow.close();
    splashWindow = null;
  }
}

// ────────────────────────────────────────────────────────────
// Main window
// ────────────────────────────────────────────────────────────
function createWindow() {
  const saved = store.get('window');
  mainWindow = new BrowserWindow({
    width: saved.width,
    height: saved.height,
    x: saved.x,
    y: saved.y,
    minWidth: 800,
    minHeight: 600,
    title: 'Bunshin',
    backgroundColor: '#0a0a0a',
    titleBarStyle: 'hiddenInset',
    trafficLightPosition: { x: 16, y: 16 },
    show: false,
    webPreferences: {
      contextIsolation: true,
      nodeIntegration: false,
      preload: path.join(__dirname, 'preload.js'),
    },
  });

  // Persist window geometry
  const persist = () => {
    if (!mainWindow || mainWindow.isDestroyed()) return;
    const [width, height] = mainWindow.getSize();
    const [x, y] = mainWindow.getPosition();
    store.set('window', { width, height, x, y });
  };
  mainWindow.on('resize', persist);
  mainWindow.on('move', persist);

  mainWindow.once('ready-to-show', () => {
    mainWindow.show();
    closeSplash();
  });

  // Open external links in the system browser
  mainWindow.webContents.setWindowOpenHandler(({ url }) => {
    if (!url.startsWith(SERVER_URL)) {
      shell.openExternal(url);
      return { action: 'deny' };
    }
    return { action: 'allow' };
  });

  // v0.9.19: hard-clear renderer cache on every launch. Honda's
  // v0.9.18 BrowserWindow was serving v0.9.16-era HTML/JS to the new
  // backend and the stale renderer froze. Sub-second op; renderer
  // resources stream from localhost anyway, so there's no cold cache
  // penalty.
  mainWindow.webContents.session.clearCache()
    .catch((err) => console.error('[bunshin] clearCache failed:', err))
    .finally(() => {
      mainWindow.loadURL(SERVER_URL);
    });
}

// ────────────────────────────────────────────────────────────
// Menu (localized, OS-language-aware)
// ────────────────────────────────────────────────────────────
function buildMenu() {
  const isMac = process.platform === 'darwin';
  const template = [
    ...(isMac ? [{
      label: 'Bunshin',
      submenu: [
        { label: t.menu.about, role: 'about' },
        { type: 'separator' },
        { label: t.menu.hide, role: 'hide' },
        { label: t.menu.hideOthers, role: 'hideOthers' },
        { label: t.menu.unhide, role: 'unhide' },
        { type: 'separator' },
        { label: t.menu.quit, role: 'quit' },
      ],
    }] : []),
    {
      label: t.menu.file,
      submenu: [
        {
          label: t.menu.newMemo,
          accelerator: 'CmdOrCtrl+N',
          click: () => mainWindow?.webContents.executeJavaScript(`
            (function() {
              const tabs = document.querySelectorAll('.tab');
              for (const t of tabs) if (t.dataset.pane === 'chat') { t.click(); break; }
              setTimeout(() => {
                const inp = document.getElementById('chat-input');
                if (inp) { inp.focus(); inp.value = '${t.menu.newMemoPrefix} '; }
              }, 100);
            })();
          `),
        },
        {
          label: t.menu.search,
          accelerator: 'CmdOrCtrl+K',
          click: () => mainWindow?.webContents.executeJavaScript(`
            (function() {
              const tabs = document.querySelectorAll('.tab');
              for (const t of tabs) if (t.dataset.pane === 'search') { t.click(); break; }
              setTimeout(() => document.getElementById('q')?.focus(), 100);
            })();
          `),
        },
        { type: 'separator' },
        isMac ? { label: t.menu.close, role: 'close' } : { label: t.menu.quit, role: 'quit' },
      ],
    },
    {
      label: t.menu.edit,
      submenu: [
        { label: t.menu.undo, role: 'undo' },
        { label: t.menu.redo, role: 'redo' },
        { type: 'separator' },
        { label: t.menu.cut, role: 'cut' },
        { label: t.menu.copy, role: 'copy' },
        { label: t.menu.paste, role: 'paste' },
        { label: t.menu.selectAll, role: 'selectAll' },
      ],
    },
    {
      label: t.menu.view,
      submenu: [
        { label: t.menu.reload, role: 'reload', accelerator: 'CmdOrCtrl+R' },
        { label: t.menu.forceReload, role: 'forceReload' },
        { label: t.menu.devTools, role: 'toggleDevTools' },
        { type: 'separator' },
        { label: t.menu.resetZoom, role: 'resetZoom' },
        { label: t.menu.zoomIn, role: 'zoomIn' },
        { label: t.menu.zoomOut, role: 'zoomOut' },
        { type: 'separator' },
        { label: t.menu.fullscreen, role: 'togglefullscreen' },
      ],
    },
    {
      label: t.menu.window,
      submenu: [
        { label: t.menu.minimize, role: 'minimize' },
        { label: t.menu.zoom, role: 'zoom' },
        ...(isMac ? [{ type: 'separator' }, { label: t.menu.front, role: 'front' }] : []),
      ],
    },
    {
      label: t.menu.help,
      submenu: [
        {
          label: t.menu.docs,
          click: () => shell.openExternal('https://github.com/Marine923/bunshin-ai/tree/main/docs'),
        },
        {
          label: t.menu.repository,
          click: () => shell.openExternal('https://github.com/Marine923/bunshin-ai'),
        },
        {
          label: t.menu.reportIssue,
          click: () => shell.openExternal('https://github.com/Marine923/bunshin-ai/issues/new'),
        },
      ],
    },
  ];
  Menu.setApplicationMenu(Menu.buildFromTemplate(template));
}

// ────────────────────────────────────────────────────────────
// App lifecycle
// ────────────────────────────────────────────────────────────
app.setName('Bunshin');

// Single-instance lock — second launch focuses the existing window
const gotLock = app.requestSingleInstanceLock();
if (!gotLock) {
  app.quit();
} else {
  app.on('second-instance', () => {
    if (mainWindow) {
      if (mainWindow.isMinimized()) mainWindow.restore();
      mainWindow.focus();
    }
  });
}

// ────────────────────────────────────────────────────────────
// IPC: native notifications from the Web UI
// ────────────────────────────────────────────────────────────
ipcMain.on('bunshin:notify', (_event, payload) => {
  if (!store.get('notifications', true)) return;
  if (!Notification.isSupported()) return;
  const { title, body } = payload || {};
  new Notification({
    title: title || 'Bunshin',
    body: body || '',
    silent: false,
  }).show();
});

// ────────────────────────────────────────────────────────────
// IPC: open the bundled CLI in Terminal.app, pre-filled
// ────────────────────────────────────────────────────────────
// The Wizard tells users to run `bunshin import-gmail` etc, but
// `bunshin` isn't on $PATH when only the .app is installed. This
// handler takes the short command (e.g. "import-gmail --full"),
// rewrites it to the bundled binary's full path, opens Terminal.app
// and pastes the command — user just hits Enter.
ipcMain.on('bunshin:run-in-terminal', (_event, payload) => {
  const { command } = payload || {};
  if (!command || typeof command !== 'string') return;
  // command examples: "import-gmail --full" / "setup-gmail --email a@b.c"
  // Strip a leading "bunshin " if the caller included it.
  const args = command.replace(/^\s*bunshin\s+/, '').trim();
  if (!args) return;
  // Locate the bundled binary inside the .app (or fall back to the
  // dev resourcesPath layout when running unpacked).
  const binPath = path.join(process.resourcesPath, 'bunshin', 'bunshin');
  // AppleScript injects the command into a fresh Terminal window.
  // Escape backslashes and double-quotes for AppleScript string.
  const fullCmd = `${binPath} ${args}`;
  const escaped = fullCmd.replace(/\\/g, '\\\\').replace(/"/g, '\\"');
  const script = `tell application "Terminal"
    activate
    do script "${escaped}"
  end tell`;
  const { spawn } = require('child_process');
  const p = spawn('osascript', ['-e', script]);
  p.on('error', (err) => console.error('[bunshin] osascript failed:', err));
});

// ────────────────────────────────────────────────────────────
// Periodic Insights → macOS / Linux native notification
// ────────────────────────────────────────────────────────────
const INSIGHTS_INTERVAL_MS = 6 * 60 * 60 * 1000;  // every 6 hours
const NOTIFIED_KEY = 'notifiedInsightIds';

async function fetchInsights() {
  try {
    return await new Promise((resolve, reject) => {
      const req = require('node:http').get(`${SERVER_URL}/api/insights`, (res) => {
        let data = '';
        res.on('data', (chunk) => (data += chunk));
        res.on('end', () => {
          try { resolve(JSON.parse(data)); } catch (e) { reject(e); }
        });
      });
      req.on('error', reject);
      req.setTimeout(5_000, () => req.destroy(new Error('timeout')));
    });
  } catch {
    return null;
  }
}

async function fetchFlashback() {
  try {
    return await new Promise((resolve, reject) => {
      const req = require('node:http').get(`${SERVER_URL}/api/flashback`, (res) => {
        let data = '';
        res.on('data', (chunk) => (data += chunk));
        res.on('end', () => {
          try { resolve(JSON.parse(data)); } catch (e) { reject(e); }
        });
      });
      req.on('error', reject);
      req.setTimeout(5_000, () => req.destroy(new Error('timeout')));
    });
  } catch {
    return null;
  }
}

function notifyKey(category, item) {
  // Stable per-insight identifier so we don't repeat notifications.
  return `${category}:${item.name || item.summary || JSON.stringify(item).slice(0, 80)}`;
}

async function pushInsightNotifications() {
  if (!store.get('notifications', true)) return;
  if (!Notification.isSupported()) return;

  const insights = await fetchInsights();
  if (!insights) return;

  const sent = new Set(store.get(NOTIFIED_KEY, []));
  const isJa = menuLanguage === 'ja';

  // High-value alerts only — over-notification is the worst sin here.
  for (const p of (insights.inactive_projects || []).slice(0, 3)) {
    const key = notifyKey('inactive', p);
    if (sent.has(key)) continue;
    if (p.days_ago < 14) continue;
    new Notification({
      title: isJa ? `🔥 ${p.name} が ${p.days_ago} 日未活動` : `🔥 ${p.name} inactive ${p.days_ago} days`,
      body: (p.description || '').slice(0, 140),
      silent: false,
    }).show();
    sent.add(key);
  }

  for (const e of (insights.upcoming_events || []).slice(0, 2)) {
    const key = notifyKey('event', e);
    if (sent.has(key)) continue;
    new Notification({
      title: isJa ? `📅 まもなく：${e.summary}` : `📅 Upcoming: ${e.summary}`,
      body: `${e.start || ''}${e.location ? ` @ ${e.location}` : ''}`,
      silent: false,
    }).show();
    sent.add(key);
  }

  // Cap remembered set to last 200 to bound storage
  const remembered = Array.from(sent).slice(-200);
  store.set(NOTIFIED_KEY, remembered);
}

function startInsightNotificationLoop() {
  if (!store.get('notifications', true)) return;
  // First check after 60s (let the server settle), then periodic.
  setTimeout(() => {
    pushInsightNotifications().catch(() => {});
    setInterval(() => pushInsightNotifications().catch(() => {}), INSIGHTS_INTERVAL_MS);
  }, 60_000);
}

// ─── Morning flashback push ──────────────────────────────────────────────
// Once per day, between 07:00 and 11:00 local time, send a single
// notification with one of the user's flashback windows ("1 year ago
// today" etc.). Idempotent via a date-stamped storage key.
const MORNING_FLASHBACK_KEY = 'lastMorningFlashbackDate';
const FLASHBACK_INTERVAL_MS = 15 * 60 * 1000;  // re-check every 15 minutes

async function pushMorningFlashback() {
  if (!store.get('notifications', true)) return;
  if (!Notification.isSupported()) return;

  const now = new Date();
  const hour = now.getHours();
  // Only fire in the morning window — never wake people up at 2am.
  if (hour < 7 || hour >= 11) return;
  const today = now.toISOString().slice(0, 10);
  if (store.get(MORNING_FLASHBACK_KEY) === today) return;

  const j = await fetchFlashback();
  if (!j || !j.windows) return;
  const populated = j.windows.filter(w => w.items && w.items.length);
  if (!populated.length) {
    // Don't notify when there's nothing to remember — mark the date so
    // we don't keep retrying every 15 minutes for nothing.
    store.set(MORNING_FLASHBACK_KEY, today);
    return;
  }
  // Prefer the most distant window (more nostalgic). Falls back to first.
  const pick = populated[populated.length - 1];
  const it = pick.items[0];
  const isJa = menuLanguage === 'ja';

  const title = isJa
    ? `${pick.label_ja} の記憶`
    : `Flashback: ${pick.label || pick.date}`;
  const body = (it.content || '').replace(/\s+/g, ' ').slice(0, 140);

  const n = new Notification({ title, body, silent: false });
  n.on('click', () => {
    if (!mainWindow || mainWindow.isDestroyed()) {
      createWindow();
      return;
    }
    mainWindow.show();
    mainWindow.focus();
    mainWindow.webContents.executeJavaScript(`
      document.querySelector('.sidebar-tab[data-pane="search"]')?.click();
    `).catch(() => {});
  });
  n.show();
  store.set(MORNING_FLASHBACK_KEY, today);
}

function startMorningFlashbackLoop() {
  if (!store.get('notifications', true)) return;
  // First check after 90s (let server settle + cover the case where
  // user launched Bunshin in the morning), then periodic.
  setTimeout(() => {
    pushMorningFlashback().catch(() => {});
    setInterval(() => pushMorningFlashback().catch(() => {}), FLASHBACK_INTERVAL_MS);
  }, 90_000);
}

function setupAutoUpdater() {
  if (!autoUpdater) return;
  if (!app.isPackaged) return;  // dev mode: skip

  autoUpdater.autoDownload = true;
  autoUpdater.autoInstallOnAppQuit = true;

  autoUpdater.on('update-available', (info) => {
    console.log('[updater] update available:', info.version);
  });
  autoUpdater.on('update-downloaded', (info) => {
    console.log('[updater] update downloaded:', info.version);
    if (mainWindow && !mainWindow.isDestroyed()) {
      const msg = menuLanguage === 'ja'
        ? `Bunshin ${info.version} の準備ができました。次回起動時に適用されます。`
        : `Bunshin ${info.version} is ready. It will be applied next launch.`;
      dialog.showMessageBox(mainWindow, {
        type: 'info',
        title: 'Bunshin',
        message: msg,
        buttons: [menuLanguage === 'ja' ? 'OK' : 'OK'],
      });
    }
  });
  autoUpdater.on('error', (err) => {
    console.error('[updater] error:', err);
  });

  // Check on startup (silent) and again every 4 hours
  autoUpdater.checkForUpdates().catch(() => {});
  setInterval(() => autoUpdater.checkForUpdates().catch(() => {}), 4 * 60 * 60 * 1000);
}

function createTray() {
  if (tray) return;
  try {
    // Template image (black ∞ on transparent) so macOS auto-tints it
    // to match the menu bar (white on dark, black on light) — same
    // treatment as system icons.
    const iconPath = path.join(__dirname, '..', 'build', 'iconTemplate.png');
    const image = nativeImage.createFromPath(iconPath);
    if (image.isEmpty()) return;
    if (process.platform === 'darwin') image.setTemplateImage(true);
    tray = new Tray(image);
    tray.setToolTip('Bunshin — 分身（個人記憶 AI）');

    const showMain = () => {
      if (!mainWindow || mainWindow.isDestroyed()) {
        createWindow();
        return;
      }
      mainWindow.show();
      mainWindow.focus();
    };
    const focusTab = (pane, focusSelector) => {
      showMain();
      setTimeout(() => {
        if (!mainWindow || mainWindow.isDestroyed()) return;
        mainWindow.webContents.executeJavaScript(`
          document.querySelector('.sidebar-tab[data-pane="${pane}"]')?.click();
          ${focusSelector ? `setTimeout(() => document.querySelector('${focusSelector}')?.focus(), 120);` : ''}
        `).catch(() => {});
      }, 60);
    };

    const contextMenu = Menu.buildFromTemplate([
      {
        label: 'Bunshin を開く',
        click: showMain,
      },
      { type: 'separator' },
      {
        label: '検索…',
        accelerator: 'CmdOrCtrl+K',
        click: () => focusTab('search', '#q'),
      },
      {
        label: 'チャットを開く',
        click: () => focusTab('chat', '#chat-input'),
      },
      {
        label: '今日のフラッシュバック',
        click: () => focusTab('search'),
      },
      { type: 'separator' },
      {
        label: 'Bunshin を終了',
        click: () => app.quit(),
      },
    ]);
    tray.setContextMenu(contextMenu);

    // Left-click toggles the main window visibility.
    tray.on('click', () => {
      if (!mainWindow || mainWindow.isDestroyed()) {
        createWindow();
        return;
      }
      if (mainWindow.isVisible() && mainWindow.isFocused()) {
        mainWindow.hide();
      } else {
        showMain();
      }
    });

    // Health polling — reviewer flagged that when the Python web server
    // dies, the menu-bar icon still looks healthy and the user has no
    // signal until they click the icon and get a blank window. Poll
    // /api/health every 30 s and reflect status in the tooltip + first
    // menu item.
    const bundledVersion = app.getVersion();
    let lastState = {healthy: true, version: bundledVersion};
    const updateTrayStatus = (state) => {
      if (!tray) return;
      const versionMismatch = state.healthy && state.version && state.version !== bundledVersion;
      let tip, top;
      if (!state.healthy) {
        tip = 'Bunshin — ⚠ Web UI 応答なし（クリックで再起動）';
        top = { label: '⚠ Web UI 停止中 — クリックで再起動', enabled: true,
                click: async () => { try { await startServer(); } catch (e) { console.error(e); } } };
      } else if (versionMismatch) {
        tip = `Bunshin — ⚠ サーバが古いコードで動作中 (${state.version} → ${bundledVersion}) クリックで再起動`;
        top = { label: `⟳ 再起動が必要 (${state.version} → ${bundledVersion})`,
                enabled: true,
                click: async () => { try { await startServer(); } catch (e) { console.error(e); } } };
      } else {
        tip = `Bunshin — 分身（個人記憶 AI） · 稼働中 v${state.version || bundledVersion}`;
        top = { label: `● 稼働中 v${state.version || bundledVersion}`, enabled: false };
      }
      tray.setToolTip(tip);
      tray.setContextMenu(Menu.buildFromTemplate([
        top,
        { type: 'separator' },
        { label: 'Bunshin を開く', click: showMain },
        { type: 'separator' },
        { label: '検索…', accelerator: 'CmdOrCtrl+K',
          click: () => focusTab('search', '#q') },
        { label: 'チャットを開く', click: () => focusTab('chat', '#chat-input') },
        { label: '今日のフラッシュバック', click: () => focusTab('search') },
        { type: 'separator' },
        { label: 'Bunshin を終了', click: () => app.quit() },
      ]));
    };
    const pingHealth = async () => {
      let next;
      try {
        const ctl = new AbortController();
        const timer = setTimeout(() => ctl.abort(), 3000);
        const r = await fetch(`http://127.0.0.1:${serverPort || 8000}/api/health`, {signal: ctl.signal});
        clearTimeout(timer);
        if (r.ok) {
          const j = await r.json().catch(() => ({}));
          next = {healthy: true, version: j.version || null};
        } else {
          next = {healthy: false, version: null};
        }
      } catch (e) {
        next = {healthy: false, version: null};
      }
      if (next.healthy !== lastState.healthy || next.version !== lastState.version) {
        lastState = next;
        updateTrayStatus(next);
      }
    };
    pingHealth();
    setInterval(pingHealth, 30 * 1000);
  } catch (e) {
    console.error('[bunshin] tray init failed:', e);
  }
}

app.whenReady().then(async () => {
  // Refresh locale now that app.getLocale() returns the real OS language.
  t = loadLocale();
  buildMenu();
  setupAutoUpdater();

  // Show splash immediately so the user has feedback while the
  // bunshin web server boots (which involves Python startup + model load).
  createSplash();
  setSplashStatus(menuLanguage === 'ja' ? 'サーバーを起動中…' : 'Starting server…');

  const started = await startServer();
  if (!started) {
    closeSplash();
    app.quit();
    return;
  }
  setSplashStatus(menuLanguage === 'ja' ? '記憶を読み込み中…' : 'Loading memories…');
  createWindow();
  createTray();
  startInsightNotificationLoop();
  startMorningFlashbackLoop();

  app.on('activate', () => {
    if (BrowserWindow.getAllWindows().length === 0) createWindow();
  });
});

app.on('window-all-closed', () => {
  if (process.platform !== 'darwin') app.quit();
});

app.on('before-quit', () => {
  stopServer();
});

app.on('will-quit', () => {
  globalShortcut.unregisterAll();
});

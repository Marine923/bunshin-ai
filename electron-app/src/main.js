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

const { app, BrowserWindow, Menu, shell, dialog, ipcMain, globalShortcut, nativeTheme, Notification } = require('electron');
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

  mainWindow.loadURL(SERVER_URL);
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
  startInsightNotificationLoop();

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

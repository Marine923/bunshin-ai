/**
 * Preload script — bridges Electron main process and the bunshin Web UI.
 *
 * Currently minimal: we just expose an electron flag so the Web UI can
 * detect it's running inside the desktop app (for future features like
 * native notifications, drag-drop file import, etc.).
 */
const { contextBridge, ipcRenderer } = require('electron');

contextBridge.exposeInMainWorld('bunshin', {
  isDesktop: true,
  platform: process.platform,
  version: process.versions.electron,
  notify: (title, body) => ipcRenderer.send('bunshin:notify', { title, body }),
  // Open Terminal.app with the bundled `bunshin` CLI pre-typed so the
  // user just hits Enter. Used by the Wizard step copy buttons —
  // ターミナルを知らない友人でも CLI が叩ける.
  runInTerminal: (command) => ipcRenderer.send('bunshin:run-in-terminal', { command }),
});

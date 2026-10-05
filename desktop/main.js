/**
 * AuditAI Desktop — shell Electron.
 *
 * Arranca e supervisiona dois processos locais e abre uma janela nativa:
 *   1. Backend  — executável PyInstaller (Django + waitress) em 127.0.0.1:8000
 *   2. Frontend — servidor Next.js standalone (via ELECTRON_RUN_AS_NODE)
 *                 em 127.0.0.1:3000, que faz proxy /api/* → Django
 *   3. Janela   — BrowserWindow a carregar http://127.0.0.1:3000
 *
 * Dev:  AUDIT_DESKTOP_DEV=1 npm start  (usa servidores já a correr e não
 *       arranca os bundled; útil com `manage.py runserver` + `next dev`)
 */
const { app, BrowserWindow, Menu, shell, dialog } = require('electron');
const { spawn } = require('child_process');
const http = require('http');
const path = require('path');
const fs = require('fs');

const BACKEND_PORT = 8000;
const FRONTEND_PORT = 3000;
const HEALTH_URL = `http://127.0.0.1:${BACKEND_PORT}/django/api/health`;
const FRONTEND_URL = `http://127.0.0.1:${FRONTEND_PORT}`;

let backendProc = null;
let frontendProc = null;
let mainWindow = null;
let quitting = false;

const isDev = process.env.AUDIT_DESKTOP_DEV === '1';

function resourcePath(rel) {
  if (isDev) return path.join(__dirname, 'resources', rel);
  return path.join(process.resourcesPath, rel);
}

/** GET com timeout curto; resolve true se responde (qualquer código < 500). */
function ping(url) {
  return new Promise((resolve) => {
    const req = http.get(url, { timeout: 1500 }, (res) => {
      res.resume();
      resolve(res.statusCode < 500);
    });
    req.on('timeout', () => { req.destroy(); resolve(false); });
    req.on('error', () => resolve(false));
  });
}

async function waitFor(url, { tries = 120, delay = 500, label = url } = {}) {
  for (let i = 0; i < tries; i++) {
    if (quitting) throw new Error('a encerrar durante o arranque');
    if (await ping(url)) return;
    await new Promise((r) => setTimeout(r, delay));
  }
  throw new Error(`timeout à espera de ${label}`);
}

function spawnBackend() {
  if (isDev) return null;
  const bin = process.platform === 'win32'
    ? path.join(resourcePath('backend'), 'audit-backend.exe')
    : path.join(resourcePath('backend'), 'audit-backend');
  if (!fs.existsSync(bin)) throw new Error(`backend não encontrado: ${bin}`);
  if (process.platform !== 'win32') fs.chmodSync(bin, 0o755);

  const proc = spawn(bin, [], {
    env: {
      ...process.env,
      AUDIT_DESKTOP_DATA_DIR: app.getPath('userData'),
      AUDIT_PORT: String(BACKEND_PORT),
      PYTHONUNBUFFERED: '1',
    },
    windowsHide: true,
  });
  proc.stdout.on('data', (d) => process.stdout.write(`[backend] ${d}`));
  proc.stderr.on('data', (d) => process.stderr.write(`[backend] ${d}`));
  proc.on('exit', (code) => {
    if (!quitting && code !== 0) {
      dialog.showErrorBox('AuditAI — backend',
        `O servidor interno terminou inesperadamente (código ${code}).\n` +
        'Reinicie a aplicação. Se persistir, reinstale.');
      app.quit();
    }
  });
  return proc;
}

function spawnFrontend() {
  if (isDev) return null;
  const serverJs = path.join(resourcePath('frontend'), 'server.js');
  if (!fs.existsSync(serverJs)) {
    throw new Error(`frontend não encontrado: ${serverJs}`);
  }
  // ELECTRON_RUN_AS_NODE transforma o binário do Electron em Node puro —
  // não exige Node.js instalado na máquina do utilizador.
  const proc = spawn(process.execPath, [serverJs], {
    env: {
      ...process.env,
      ELECTRON_RUN_AS_NODE: '1',
      PORT: String(FRONTEND_PORT),
      HOSTNAME: '127.0.0.1',
      NODE_ENV: 'production',
    },
    windowsHide: true,
  });
  proc.stdout.on('data', (d) => process.stdout.write(`[frontend] ${d}`));
  proc.stderr.on('data', (d) => process.stderr.write(`[frontend] ${d}`));
  proc.on('exit', (code) => {
    if (!quitting && code !== 0) {
      dialog.showErrorBox('AuditAI — interface',
        `A interface web terminou inesperadamente (código ${code}).`);
      app.quit();
    }
  });
  return proc;
}

function createWindow() {
  mainWindow = new BrowserWindow({
    width: 1440,
    height: 900,
    minWidth: 1024,
    minHeight: 700,
    show: false,
    autoHideMenuBar: true,
    backgroundColor: '#0f172a',
    title: 'AuditAI',
    icon: path.join(__dirname, 'build', 'icon.png'),
    webPreferences: {
      contextIsolation: true,
      nodeIntegration: false,
      sandbox: true,
      spellcheck: false,
    },
  });

  // ligações externas (target=_blank / window.open) abrem no browser do SO
  mainWindow.webContents.setWindowOpenHandler(({ url }) => {
    if (url.startsWith(FRONTEND_URL) || url.startsWith(`http://127.0.0.1:${BACKEND_PORT}`)) {
      return { action: 'allow', overrideBrowserWindowOptions: { autoHideMenuBar: true } };
    }
    shell.openExternal(url);
    return { action: 'deny' };
  });

  mainWindow.once('ready-to-show', () => mainWindow.show());
  mainWindow.loadURL(FRONTEND_URL);
  mainWindow.on('closed', () => { mainWindow = null; });
}

function killChildren() {
  quitting = true;
  for (const p of [frontendProc, backendProc]) {
    if (p && p.exitCode === null && !p.killed) {
      try { p.kill(process.platform === 'win32' ? undefined : 'SIGTERM'); } catch (_) {}
    }
  }
}

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

  app.whenReady().then(async () => {
    Menu.setApplicationMenu(null); // UI limpa, sem menu padrão
    try {
      backendProc = spawnBackend();
      frontendProc = spawnFrontend();
      await waitFor(HEALTH_URL, { label: 'backend Django' });
      await waitFor(FRONTEND_URL, { label: 'interface Next.js' });
      createWindow();
    } catch (err) {
      dialog.showErrorBox('AuditAI — arranque',
        `Falha ao iniciar os serviços locais:\n\n${err.message}`);
      app.quit();
    }
  });

  app.on('window-all-closed', () => { killChildren(); app.quit(); });
  app.on('before-quit', killChildren);
  process.on('exit', killChildren);
}

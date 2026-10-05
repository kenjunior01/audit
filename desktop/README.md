# AuditAI Desktop

Aplicação desktop do AuditAI: **Electron** (janela nativa) + **backend Django
embutido** (executável PyInstaller com waitress) + **frontend Next.js
standalone** (corre com o Node embutido do Electron — não exige Node na
máquina do utilizador).

```
┌─────────────────────────── AuditAI Desktop ───────────────────────────┐
│  BrowserWindow (Electron)                                             │
│    └─ http://127.0.0.1:3000   ← frontend Next standalone              │
│              └─ proxy /api/* ──→  127.0.0.1:8000 (Django + waitress)  │
│                                        └─ SQLite em userData          │
└───────────────────────────────────────────────────────────────────────┘
```

## Primeira execução

O backend (audit-backend) automaticamente:

1. Cria a pasta de dados do utilizador (`%APPDATA%/AuditAI` no Windows,
   `~/.config/AuditAI` no Linux, `~/Library/Application Support/AuditAI`
   no macOS — via `app.getPath('userData')`).
2. Gera a `SECRET_KEY` persistente.
3. Corre as migrações na base SQLite local.
4. Semeia dados de demonstração (idempotente): 120 transações, 20 alertas,
   6 casos, regras e o utilizador **demo@audit.pt / demo1234** (papel admin).

## Desenvolvimento

```bash
# 1) backend normal (fora do PyInstaller):
cd django_app && python manage.py migrate && python manage.py runserver 127.0.0.1:8000

# 2) frontend normal:
cd frontend && npm run dev   # ou npm start (produção)

# 3) shell Electron em modo dev (não arranca os processos bundled):
cd desktop && npm install && AUDIT_DESKTOP_DEV=1 npm start
```

## Build local (Linux, exemplo)

```bash
# backend
pip install -r requirements.txt pyinstaller==6.10.0
cd desktop-backend && pyinstaller audit-backend.spec --noconfirm
# → desktop-backend/dist/audit-backend

# frontend standalone
cd ../frontend && npm ci && npm run build
mkdir -p ../desktop/resources/frontend
cp -r .next/standalone/* ../desktop/resources/frontend/
cp -r .next/static ../desktop/resources/frontend/.next/static
cp -r public ../desktop/resources/frontend/public 2>/dev/null || true
cp ../desktop-backend/dist/audit-backend ../desktop/resources/backend/

# electron
cd ../desktop && npm install && npm run dist
# → desktop/dist/AuditAI-*.AppImage
```

## Releases automáticos

O workflow **Release Desktop** (`.github/workflows/release-desktop.yml`)
constrói, num `workflow_dispatch` ou numa tag `v*`:

| Plataforma | Artefactos |
|---|---|
| Windows | `AuditAI Setup x64.exe` (NSIS) + portable `.exe` |
| Linux | `AuditAI-*.AppImage` |
| macOS | `AuditAI-*.dmg` |

Em `workflow_dispatch`, os instaladores são publicados numa release
prerelease `desktop-build-<run_number>`; em tags `v*`, o electron-builder
publica diretamente na release da tag.

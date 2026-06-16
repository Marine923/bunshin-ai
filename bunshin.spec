# PyInstaller spec for the bunshin CLI.
#
# Builds a self-contained one-folder distribution at dist/bunshin/ which
# we then ship inside the Electron app under Contents/Resources/bunshin.
#
# Build: ~/.bunshin/venv/bin/pyinstaller bunshin.spec

from PyInstaller.utils.hooks import collect_all, collect_submodules

# Packages whose data files / .so binaries / hidden imports we need.
_PACKAGES = [
    "fastembed",         # ONNX text-embedding runtime
    "sqlite_vec",        # vector extension binary
    "tiktoken",
    "pydantic_core",
    "mcp",
    "fastapi",
    "uvicorn",
    "starlette",
    "watchdog",
    "icalendar",
    "pypdf",
    "docx",              # python-docx
    "click",
    "rich",
    "httpx",
    "numpy",
    "PIL",               # Pillow for photo EXIF
    "onnxruntime",
    "huggingface_hub",
    "tokenizers",
]

datas = []
binaries = []
hiddenimports = []

for pkg in _PACKAGES:
    try:
        d, b, h = collect_all(pkg)
        datas += d
        binaries += b
        hiddenimports += h
    except Exception:
        pass

# Bunshin's own submodules (cli, ingestion.*, web.*, etc.)
hiddenimports += collect_submodules("bunshin")

a = Analysis(
    ["src/bunshin/__main__.py"],
    pathex=["src"],
    binaries=binaries,
    datas=datas,
    hiddenimports=hiddenimports,
    hookspath=[],
    runtime_hooks=[],
    excludes=[],
    noarchive=False,
)

pyz = PYZ(a.pure)

exe = EXE(
    pyz,
    a.scripts,
    [],
    exclude_binaries=True,
    name="bunshin",
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=False,
    console=True,
    disable_windowed_traceback=False,
    target_arch=None,
    codesign_identity=None,
    entitlements_file=None,
)

coll = COLLECT(
    exe,
    a.binaries,
    a.datas,
    strip=False,
    upx=False,
    upx_exclude=[],
    name="bunshin",
)

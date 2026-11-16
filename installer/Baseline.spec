# PyInstaller spec for the Baseline desktop app.
# Build from the project root:  python -m PyInstaller installer/Baseline.spec --noconfirm   (build.ps1 does this)
from pathlib import Path

ROOT = Path(SPECPATH).resolve().parent

datas = [
    (str(ROOT / "web" / "dist"), "web/dist"),
    (str(ROOT / "data" / "rules"), "data/rules"),
    (str(ROOT / "data" / "ledger"), "data/ledger"),
    (str(ROOT / "data" / "results"), "data/results"),
    (str(ROOT / "engine"), "engine"),
    (str(ROOT / "backend"), "backend"),
    (str(ROOT / ".env.example"), "."),
]
pem = ROOT / "desktop" / "license_public_key.pem"
if pem.exists():
    datas.append((str(pem), "desktop"))

hidden = [
    "uvicorn.logging", "uvicorn.loops.auto", "uvicorn.protocols.http.auto", "uvicorn.protocols.websockets.auto",
    "uvicorn.lifespan.on", "reportlab.pdfbase._fontdata", "cryptography.hazmat.primitives.asymmetric.ed25519",
    "scipy.stats", "sklearn.linear_model", "pyarrow", "nba_api.stats.endpoints", "webview.platforms.edgechromium",
    "backend.app.main", "backend.app.routers.api", "backend.app.routers.auth",
]

a = Analysis(
    [str(ROOT / "desktop" / "launcher.py")],
    pathex=[str(ROOT), str(ROOT / "engine"), str(ROOT / "desktop")],
    datas=datas,
    hiddenimports=hidden,
    excludes=["tkinter", "torch", "tensorflow", "xgboost", "lightgbm", "IPython", "notebook", "PyQt5", "PyQt6", "PySide6", "pytest", "matplotlib"],
    noarchive=False,
)
pyz = PYZ(a.pure)
icon = ROOT / "assets" / "icon.ico"
exe = EXE(pyz, a.scripts, [], exclude_binaries=True, name="Baseline", console=False, icon=str(icon) if icon.exists() else None)
coll = COLLECT(exe, a.binaries, a.datas, strip=False, upx=False, name="Baseline")

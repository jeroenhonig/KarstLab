# -*- mode: python ; coding: utf-8 -*-
"""PyInstaller spec for KarstLab Windows GUI application."""

from pathlib import Path
import os

project_root = Path(SPECPATH).parent.parent
src_dir = project_root / "src"

# Determine PROJ data directory
try:
    import pyproj
    proj_data = Path(pyproj.datadir.get_data_dir())
except (ImportError, Exception):
    proj_data = None

# Determine GDAL data directory (bundled with rasterio)
try:
    import rasterio
    gdal_data = None
    # GDAL data might be in rasterio installation
except ImportError:
    gdal_data = None

# WhiteboxTools binary path (if available)
wbt_bin = None
wbt_search_paths = [
    Path.home() / ".local" / "bin" / "whitebox_tools.exe",
    Path("C:\\Program Files\\WhiteboxTools\\whitebox_tools.exe"),
    Path("C:\\Program Files (x86)\\WhiteboxTools\\whitebox_tools.exe"),
]
for path in wbt_search_paths:
    if path.exists():
        wbt_bin = path
        break

# Collect data files
datas = [
    # Resource directories
    (str(src_dir / "karstlab" / "resources" / "regions"), "karstlab/resources/regions"),
    (str(src_dir / "karstlab" / "resources" / "schemas"), "karstlab/resources/schemas"),
    (str(src_dir / "karstlab" / "resources" / "i18n"), "karstlab/resources/i18n"),
    (str(src_dir / "karstlab" / "resources" / "templates"), "karstlab/resources/templates"),
]

# Add PROJ data if found
if proj_data and proj_data.exists():
    datas.append((str(proj_data), "proj"))

# Add GDAL data if found
if gdal_data and gdal_data.exists():
    datas.append((str(gdal_data), "gdal"))

# Collect binaries
binaries = []
if wbt_bin:
    binaries.append((str(wbt_bin), "bin"))

# Hidden imports for dependencies
hiddenimports = [
    # Rasterio and GDAL
    "rasterio",
    "rasterio._base",
    "rasterio.crs",
    "rasterio.features",
    "rasterio.mask",
    "rasterio.plot",
    # PROJ and PyProj
    "pyproj",
    "pyproj.exceptions",
    # GeoPandas
    "geopandas",
    "shapely",
    # PySide6
    "PySide6.QtCore",
    "PySide6.QtGui",
    "PySide6.QtWidgets",
    "PySide6.QtWebEngineWidgets",
    "PySide6.QtSvg",
    # NumPy and SciPy
    "numpy",
    "scipy",
    # KarstLab modules
    "karstlab.presentation.app",
    "karstlab.presentation.widgets",
    "karstlab.domain.models",
    "karstlab.data.repository",
]

a = Analysis(
    [str(src_dir / "karstlab" / "presentation" / "app.py")],
    pathex=[str(src_dir)],
    binaries=binaries,
    datas=datas,
    hiddenimports=hiddenimports,
    hookspath=[str(project_root / "packaging" / "hooks")],
    hooksconfig={},
    runtime_hooks=[str(project_root / "packaging" / "runtime_hooks" / "set_proj_data.py")],
    excludes=[
        "matplotlib",
        "pytest",
        "sphinx",
        "IPython",
    ],
    noarchive=False,
)

pyz = PYZ(a.pure, a.zipped_data, cipher=None)

exe = EXE(
    pyz,
    a.scripts,
    [],
    exclude_binaries=True,
    name="KarstLab",
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=False,
    console=False,
    target_arch=None,
    icon=str(project_root / "packaging" / "icons" / "karstlab.ico")
    if (project_root / "packaging" / "icons" / "karstlab.ico").exists()
    else None,
)

coll = COLLECT(
    exe,
    a.binaries,
    a.zipfiles,
    a.datas,
    strip=False,
    upx=False,
    upx_exclude=[],
    name="KarstLab",
)

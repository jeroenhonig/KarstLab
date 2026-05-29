"""Runtime hook: set PROJ_DATA and GDAL_DATA environment variables.

When running as a PyInstaller bundle, sets environment variables to point
to the bundled PROJ and GDAL data directories.
"""

import os
import sys
from pathlib import Path

if getattr(sys, "frozen", False) and hasattr(sys, "_MEIPASS"):
    # Running as PyInstaller bundle
    bundle_dir = Path(sys._MEIPASS)  # type: ignore[attr-defined]

    # Set PROJ environment variables
    proj_data = bundle_dir / "proj"
    if proj_data.exists():
        os.environ["PROJ_DATA"] = str(proj_data)
        os.environ["PROJ_LIB"] = str(proj_data)

    # Set GDAL environment variables
    gdal_data = bundle_dir / "gdal"
    if gdal_data.exists():
        os.environ["GDAL_DATA"] = str(gdal_data)

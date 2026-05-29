"""PyInstaller hook for rasterio.

Ensures GDAL and rasterio data files are bundled.
"""

from PyInstaller.utils.hooks import collect_data_files

# Collect all data files from rasterio (includes GDAL data)
datas = collect_data_files("rasterio")

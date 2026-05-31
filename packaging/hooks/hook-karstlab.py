"""PyInstaller hook for karstlab package.

Ensures all karstlab data files and submodules are collected.
"""

from PyInstaller.utils.hooks import collect_data_files, collect_submodules

# Collect all resource files from karstlab package
datas = collect_data_files("karstlab")

# Collect all submodules to ensure dynamic imports are included
hiddenimports = collect_submodules("karstlab")

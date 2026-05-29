PYTHON ?= python3

.PHONY: test lint typecheck check doctor schemas check-schemas translate icons package-macos package-windows package clean

test:
	$(PYTHON) -m pytest

lint:
	$(PYTHON) -m ruff check src tests

typecheck:
	$(PYTHON) -m mypy src/karstlab tests

check: lint typecheck test

doctor:
	$(PYTHON) -m karstlab.cli.main doctor

schemas:
	$(PYTHON) -m karstlab.data.schema_export

check-schemas:
	$(PYTHON) -m karstlab.data.schema_export --check

translate:
	.venv/bin/pyside6-lupdate src/karstlab/presentation/*.py -ts \
	    src/karstlab/resources/i18n/karstlab_en.ts \
	    src/karstlab/resources/i18n/karstlab_nl.ts \
	    src/karstlab/resources/i18n/karstlab_fr.ts
	.venv/bin/pyside6-lrelease \
	    src/karstlab/resources/i18n/karstlab_en.ts \
	    src/karstlab/resources/i18n/karstlab_nl.ts \
	    src/karstlab/resources/i18n/karstlab_fr.ts

icons:
	$(PYTHON) packaging/create_icons.py

package-macos: translate icons
	PYINSTALLER_CONFIG_DIR=.pyinstaller $(PYTHON) -m PyInstaller packaging/karstlab_gui.spec --noconfirm
	hdiutil create -volname KarstLab -srcfolder dist/KarstLab.app -ov -format UDZO dist/KarstLab.dmg

package-windows: translate icons
	PYINSTALLER_CONFIG_DIR=.pyinstaller $(PYTHON) -m PyInstaller packaging/karstlab_gui_win.spec --noconfirm

package: package-macos

clean:
	rm -rf .mypy_cache .pytest_cache .ruff_cache .pyinstaller build dist *.dmg

PYTHON ?= python3

.PHONY: test lint typecheck check doctor package clean

test:
	$(PYTHON) -m pytest

lint:
	$(PYTHON) -m ruff check src tests

typecheck:
	$(PYTHON) -m mypy src/karstlab tests

check: lint typecheck test

doctor:
	$(PYTHON) -m karstlab.cli.main doctor

package:
	PYINSTALLER_CONFIG_DIR=.pyinstaller $(PYTHON) -m PyInstaller packaging/karstlab_gui.spec --noconfirm

clean:
	rm -rf .mypy_cache .pytest_cache .ruff_cache .pyinstaller build dist

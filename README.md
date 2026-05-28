# KarstLab

KarstLab is a cross-platform desktop GIS application for karst terrain analysis.

The project is currently in the v0.1.0 setup phase. The v1.0.0 target is documented in:

- `docs/architecture/`
- `docs/development/v1.0.0-release-plan.md`
- `docs/development/agent-orchestration.md`

## Development

```bash
python3.12 -m venv .venv
source .venv/bin/activate
python -m pip install -U pip
python -m pip install -e ".[dev,package]"
make test
make lint
make typecheck
make doctor
make package
make clean
```

KarstLab development and packaging should use Python 3.12. The project metadata allows newer
Python versions, but the geospatial dependency stack depends on C-extension wheels that are most
reliably available on Python 3.12.

Network-dependent tests must be marked with `@pytest.mark.network` and are not part of the default release gate.

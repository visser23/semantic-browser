# Dependency Guide

## Runtime Dependency Matrix

| Use Case | Install Command | Extra Dependencies Pulled |
|---|---|---|
| Attach to existing browser stack | `pip install semantic-browser` | `pydantic`, `click`, `PyYAML` |
| Managed browser lifecycle | `pip install "semantic-browser[managed]"` | core + `playwright` |
| Local HTTP service | `pip install "semantic-browser[server]"` | core + `fastapi`, `uvicorn` |
| Full development setup | `pip install "semantic-browser[full]"` | managed + server + test tooling |

## Hard Requirements

- Python: `>=3.11`
- Browser substrate (v1): Chromium / Chrome only
- Browser automation API: Playwright async API

## Browser Bootstrap

Managed mode requires Chromium bundle installation:

```bash
semantic-browser install-browser
```

## Verify Environment

```bash
semantic-browser doctor
```

Expected output includes:

- python version
- `playwright: true` (for managed mode)

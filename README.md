# PixHerder

Find and clean duplicate images on Windows. Native desktop app with a browser-style interface.

## What it does

- **Exact matching** -- byte-for-byte identical file detection via MD5 checksums
- **Visual matching** -- finds photos that look the same even if cropped, resized, or re-saved (perceptual hashing)
- **Safe workflow** -- copies files to a staging area first; originals are never touched until you decide
- **Recovery** -- removed files go to the Windows Recycle Bin or a local folder, never permanently deleted without your say-so
- **OneDrive aware** -- detects OneDrive paths and prompts you to pause sync before bulk operations
- **HEIC/HEIF support** -- handles iPhone photos natively via pillow-heif

## Quick start

1. Download or clone this repository
2. Run `setup.bat` -- it downloads an embedded Python, installs dependencies, and creates a desktop shortcut
3. Double-click the shortcut or `launch.vbs`

No system Python required. Everything runs from the project folder.

## Requirements

- Windows 10 version 1803+ or Windows 11
- Microsoft Edge WebView2 Runtime (included in Windows 11; setup.bat checks for it)
- ~200 MB disk space for the embedded Python + dependencies

## How it works

PixHerder runs a local web server on `127.0.0.1:8787` and opens a native window via pywebview. All processing happens on your machine -- nothing is uploaded or sent anywhere.

### Workflow

1. **Migrate** -- Import photos from a source folder into a staging area
2. **Scan** -- Run exact and/or perceptual duplicate detection
3. **Review** -- Browse duplicate groups side by side, mark files to keep or remove
4. **Finalize** -- Send cleaned files home and remove the workspace

Four workflow modes (Easy, Autonomous, Hybrid, Manual) let you choose your level of control.

## Architecture

```
pixherder_app.py          Entry point (pywebview native window)
engine/                   Core logic
  scanner.py              File discovery
  hasher.py               MD5 + perceptual hashing
  comparator.py           Duplicate group detection
  actions.py              File move/delete operations
  staging.py              Safe copy + OneDrive handling
  config.py               Settings + atomic JSON writes
web/                      UI layer
  index.html              Single-page app (vanilla HTML/CSS/JS)
  server.py               Internal HTTP server (images + static files)
  bridge.py               pywebview API bridge
  workers.py              Background thread management
  routes_*.py             HTTP route handlers
tests/                    Unit + E2E tests
setup.bat                 One-click installer
```

## Development

Run the app in debug mode with a console:

```
python pixherder_app.py --support-mode
```

Run the test suite:

```
python -m pytest tests/
```

Run the E2E workflow test:

```
python tests/test_e2e.py
```

## License

Apache License 2.0. See [LICENSE](LICENSE).

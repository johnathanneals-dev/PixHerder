# DupeFinder - Full-Stack Frontend Build Prompt

## Project Overview

Build a unified web-based frontend for DupeFinder, a duplicate image detection tool. The app should replace all command-line interaction with a polished browser-based UI. It runs as a local Python web server (no cloud, no accounts, no external services). Everything runs on the user's machine.

The project lives in `C:\Projects\Duped\`. There are existing Python scripts that contain the core logic — you should refactor and integrate them into a single cohesive application, not start from scratch.

## Existing Codebase (in C:\Projects\Duped\)

Review these files before writing any code:

- **dupefinder.py** — Core scanning engine. Has MD5 exact matching, perceptual hashing (pHash via imagehash library), file discovery, grouping logic, and actions (report, move, delete, JSON export). The `pick_original()` function decides which file to keep (currently: largest file).
- **reviewer.py** — Local web server that serves an HTML/JS/CSS single-page app for reviewing duplicate groups side-by-side. Serves images via `/image?path=` endpoint. Has keyboard shortcuts, lightbox zoom, mark-for-move/skip workflow, and exports a PowerShell move script. The UI design is dark-themed with green (#6ee7b7) for KEEP and red (#f87171) for DUPE badges. This is the design language to build on.
- **oddball_finder.py** — Verification tool that re-hashes KEEP/DUPE pairs and flags weak matches (high hamming distance) as potential false positives.
- **perceptual_report.json** — Example output from a scan (5,597 groups, ~9,500 dupes).

## Tech Stack

- **Backend**: Python 3.13+ (user also has 3.14 installed but it has bugs — default to 3.13). Use the built-in `http.server` module or Flask if you prefer, but keep dependencies minimal. No database — use JSON files for persistence.
- **Frontend**: Single-page app served by the Python backend. Vanilla HTML/CSS/JS (no React, no build tools, no npm). The user opens it in Edge or Chrome.
- **Dependencies**: Pillow, imagehash (already installed). Minimize new dependencies.
- **OS**: Windows 11. File paths use backslashes. The user has OneDrive syncing their Pictures folder which causes file locking issues — use copy-based approaches instead of shutil.move, and handle permission errors gracefully per-file (don't crash on one failure).

## Critical Environment Notes

1. **Controlled Folder Access** is enabled in Windows Defender. Python executables at `C:\Program Files\Python313\python.exe` and `C:\Users\repom\AppData\Local\Programs\Python\Python314\python.exe` have been whitelisted. If the app creates files and gets "FileNotFoundError: [Errno 2]" or "Access is denied", this is likely the cause — remind the user to whitelist the Python executable.
2. **OneDrive** syncs `C:\Users\repom\OneDrive\Pictures`. Files in this folder can be locked by OneDrive sync. This causes "Access is denied" and "Invalid argument" errors during file operations. Hard-won lessons:
   - Never use `shutil.move()` on OneDrive paths — use `shutil.copy2()` + `os.remove()` or PowerShell `Copy-Item`/`Remove-Item`.
   - Always use try/except PER-FILE for move/copy/delete operations. Never let one bad file crash the whole batch.
   - `pick_original()` must handle missing files gracefully — during bulk moves, earlier operations can remove files referenced by later groups. Wrap `stat()` calls in try/except and skip files that no longer exist.
   - `action_move()` must check that `pick_original()` returned a valid result (not None) before proceeding.
   - The move destination folder must be OUTSIDE OneDrive paths. Use `C:\Temp\` or similar.
   - OneDrive will try to restore deleted/moved files if sync is active. The app MUST auto-pause OneDrive before bulk operations: use `taskkill /f /im OneDrive.exe` to stop sync, then `Start-Process "$env:LOCALAPPDATA\Microsoft\OneDrive\OneDrive.exe"` to restart after. Prompt the user with a confirmation dialog before doing this.
   - If the user clicks "Keep" on OneDrive restore prompts, all cleanup work gets undone. The UI should warn about this.
3. **Portmaster** firewall is running. The local web server needs to bind to `127.0.0.1` (not `0.0.0.0`). Port 8787 has a firewall rule allowing it. Stick with that port or document how to add a new rule.
4. **ASCII only in Python source files.** Python 3.14 chokes on Unicode characters (em-dashes, emoji, fancy quotes) in .py files. Keep all source files pure ASCII.

## Application Architecture

### Single entry point
```
python dupefinder_app.py
```
This starts the web server and opens the browser. Everything else happens in the UI.

### Pages / Views

**1. Dashboard (Home)**
- Welcome screen with quick stats if previous scan results exist (groups found, space reclaimable, last scan date).
- Big "Start New Scan" button.
- List of previous scan results (JSON reports) with options to review or delete them.

**2. Scan Configuration**
- Folder picker: text input for the path (no native file picker in browser — just a text field with a "Browse" hint telling the user to paste a path).
- Scan mode: Radio buttons for Exact / Perceptual / Both.
- Perceptual threshold: Slider (0-20) with labels (0 = identical, 5 = near-duplicate, 10 = similar, 15+ = loose).
- Recursive toggle: checkbox, default on.
- "Start Scan" button.

**3. Scan Progress**
- Real-time progress updates via server-sent events (SSE) or polling.
- Show: current stage (MD5 hashing / pHash hashing / comparing), files processed / total, elapsed time, estimated time remaining.
- Progress bar.
- Allow cancellation.
- When complete, show summary (groups found, space reclaimable) and a "Review Results" button.

**4. Review (the existing reviewer, enhanced)**
- Side-by-side image comparison with KEEP (green) and DUPE (red) badges.
- Image cards showing: thumbnail, filename, folder path, file size, dimensions, date modified.
- Lightbox zoom on click.
- Navigation: prev/next arrows, keyboard shortcuts (arrow keys, S to skip, M to mark), jump-to-group input.
- Per-group actions: Skip (keep all) / Mark dupes for move / Mark dupes for delete.
- Bulk actions: "Mark All for Move", "Mark All for Delete", "Skip All".
- Filter/sort options: sort by group size, sort by reclaimable space, filter by distance range, show only unreviewed.
- Search: filter groups by filename or folder path.
- Progress indicator: "Reviewed X / Y groups | Marked Z for move".
- The distance score should be displayed on each group (for perceptual matches) so the user can gauge confidence.

**5. Action / Execute**
- Summary of pending actions (X files to move, Y files to delete, Z space to reclaim).
- Destination folder picker for moves.
- "Execute" button with confirmation dialog.
- Real-time progress of file operations.
- Error log for any files that failed (with reason).
- Results summary when complete.

**6. Oddball Verification**
- After a move/delete operation, option to run the oddball checker.
- Shows pairs sorted by distance (weakest matches first).
- Uses the same reviewer UI but filtered to only suspicious pairs.
- Option to "rescue" files back from the dupes folder.

**7. Settings**
- Default scan threshold.
- Default move destination.
- Keep strategy: dropdown (largest file / oldest file / newest file / shortest filename).
- Supported file extensions: editable list.
- Server port.

### API Endpoints

The backend should expose a REST-ish JSON API:

- `GET /` — Serve the SPA HTML.
- `GET /api/scans` — List previous scan results.
- `POST /api/scan/start` — Start a new scan (params: directory, mode, threshold, recursive).
- `GET /api/scan/progress` — SSE stream or poll for scan progress.
- `POST /api/scan/cancel` — Cancel a running scan.
- `GET /api/groups?report=<filename>` — Get groups from a report.
- `GET /api/image?path=<filepath>` — Serve an image file (with caching headers).
- `POST /api/action/move` — Move marked files.
- `POST /api/action/delete` — Delete marked files.
- `POST /api/action/rescue` — Move a file back from dupes folder to original location.
- `GET /api/oddball/run?report=<filename>` — Run oddball verification.
- `GET /api/settings` / `POST /api/settings` — Read/write settings.

### Data Storage

- Scan results: JSON files in `C:\Projects\Duped\scans\` directory, named with timestamp (e.g., `scan_2026-03-16_143022.json`).
- Settings: `C:\Projects\Duped\settings.json`.
- Action logs: `C:\Projects\Duped\logs\` directory.

## UI Design Requirements

- **Dark theme** matching the existing reviewer: background #0a0a0c, surfaces #131318 / #1a1a22, borders #2a2a35, text #e8e8ed, accent green #6ee7b7, danger red #f87171.
- **Clean and minimal.** No clutter. Generous spacing. The user is not technical — everything should be obvious.
- **Responsive** enough to work on a laptop screen (1366x768 minimum).
- **No external font CDNs** — use system fonts (`-apple-system, BlinkMacSystemFont, 'Segoe UI', sans-serif`) and `monospace` for data. The existing reviewer tried to load Google Fonts which may be blocked by Portmaster.
- **No external CDN dependencies at all** — everything must work offline / on localhost with no external network requests.
- **Smooth transitions** between views (simple CSS transitions, nothing heavy).
- **Toast notifications** for success/error messages instead of alert() dialogs.
- **Confirmation dialogs** for destructive actions (delete, bulk operations) — built into the UI, not browser alert().

## Scan Engine Improvements

While refactoring the scan engine, make these improvements:

1. **Progress reporting**: The scan functions currently print to stdout. Refactor them to yield progress updates that can be sent to the frontend.
2. **Cancellation**: Add a threading event or flag that the scan loop checks periodically, allowing the user to cancel mid-scan.
3. **Performance**: The perceptual comparison is O(n^2). For 22,000+ images this takes a long time. Consider optimizations like:
   - Size pre-filter: only compare images within a similar file size range.
   - Hash bucketing: group by coarse hash prefix before doing pairwise comparison.
   - Or just add a clear progress indicator so the user knows it's working.
4. **HEIC support**: Currently fails on .heic files. If pillow-heif is installable, add it. Otherwise, gracefully skip with a count of skipped files shown in the UI.
5. **Error resilience**: Never crash on a single bad file. Log the error, skip it, continue. Specific crash points discovered in testing:
   - `md5_hash()`: crashes on corrupted or OneDrive-locked files with "OSError: [Errno 22] Invalid argument". Wrap in try/except, return None on failure.
   - `find_exact_duplicates()`: must skip None results from md5_hash().
   - `perceptual_hash()`: already has try/except (use this as the pattern for everything else).
   - `pick_original()`: crashes with FileNotFoundError when calling `p.stat().st_size` on files that were already moved by earlier operations in the same batch. Wrap each stat() in try/except, collect only valid files, return None if no valid files remain.
   - `action_move()`: must check that pick_original() returned a valid result (not None) before proceeding. Each individual file copy/delete must be in its own try/except so one failure doesn't stop the batch.
   - General rule: every function that touches the filesystem must handle failures gracefully. The UI should show a count of skipped/failed files alongside successful ones.

## File Structure

```
C:\Projects\Duped\
  dupefinder_app.py          # Main entry point — starts server, opens browser
  engine/
    __init__.py
    scanner.py               # Image discovery
    hasher.py                # MD5 and perceptual hashing
    comparator.py            # Duplicate grouping logic
    actions.py               # Move, delete, copy, rescue operations
    oddball.py               # Oddball verification
  web/
    __init__.py
    server.py                # HTTP server and API routes
    index.html               # The SPA (single file, all HTML/CSS/JS inline)
  scans/                     # Saved scan results (JSON)
  logs/                      # Action logs
  settings.json              # User preferences
```

## Testing

After building, test with:
1. A scan of `C:\Users\repom\OneDrive\Pictures` (22,700+ images).
2. Verify exact duplicates are found.
3. Verify perceptual duplicates are found.
4. Verify the reviewer displays images correctly.
5. Verify move operations work (pause OneDrive first).
6. Verify the oddball finder flags weak matches.
7. Verify the app handles errors gracefully (locked files, missing files, corrupted images).

## Summary

The goal is: the user runs one command (`python dupefinder_app.py`), a browser opens, and they can scan folders, review duplicates visually, and clean them up — all without touching the command line again. Keep it simple, keep it robust, and match the dark polished aesthetic of the existing reviewer UI.
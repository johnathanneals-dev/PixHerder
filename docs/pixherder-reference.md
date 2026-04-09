# PixHerder Reference

API endpoints, detailed feature specs, and file structure. Load when needed, not every session.

## API Endpoints

- GET / — Serve the SPA
- GET /api/scans — List previous scan results
- POST /api/scan/start — Start a new scan
- GET /api/scan/progress — SSE stream for scan progress
- POST /api/scan/cancel — Cancel a running scan
- GET /api/groups?report=<filename> — Get groups from a report
- GET /api/image?path=<filepath> — Serve an image file (cached)
- POST /api/action/move — Move marked files
- POST /api/action/delete — Delete marked files
- POST /api/action/rescue — Restore a file from dupes folder
- GET /api/action/progress — SSE stream for action progress
- GET /api/oddball/run — Run oddball verification
- GET /api/oddball/progress — SSE stream for oddball progress
- GET /api/settings / POST /api/settings — Read/write settings
- POST /api/scans/delete — Delete a scan result
- GET /api/scan/check-resume — Check for resumable checkpoint
- GET /api/activity / POST /api/activity/clear — Activity log
- POST /api/staging/check — Detect OneDrive path, check existing staging
- POST /api/staging/start — Begin staging copy from OneDrive
- GET /api/staging/progress — SSE stream for staging progress
- POST /api/staging/cancel — Cancel staging
- GET /api/staging/status — Current staging session info
- POST /api/staging/syncback — Apply deletions back to OneDrive
- GET /api/staging/syncback/progress — SSE stream for sync-back
- POST /api/staging/cleanup — Delete staging folder
- GET /api/browse — Paginated file browser (restricted to staging/dupes dirs)
- GET /api/folders/status — File counts for staging and dupes folders
- POST /api/browser/delete — Delete a single file from browser
- POST /api/browser/delete-folder — Delete a folder from browser
- POST /api/browser/open-explorer — Open folder in Windows File Explorer
- POST /api/browser/open-recycle-bin — Open Windows Recycle Bin
- POST /api/decisions/save — Save review decisions for a scan report
- GET /api/decisions/load?report=X — Load saved review decisions
- POST /api/staging/recycle — Move dupes into staging for re-review (Rescue & Review)
- POST /api/dupes/purge — Delete all files in dupes folder
- POST /api/staging/recycle-bin — Send files to Windows Recycle Bin (accepts folder: "staging" or "dupes")
- POST /api/dupes/promote — Move all dupes to keepers folder
- POST /api/consolidate — Move dupes + keepers back into staging (Start Over)
- GET /api/browse-folders — List subfolders at a path (for folder picker)
- POST /api/staging/reset — Reset in-memory staging session (no file ops)
- GET /api/recovery/status — Check if recovery archive has files
- GET /api/recovery/list — List files in recovery archive slots
- POST /api/recovery/restore — Restore files from recovery archive
- POST /api/recovery/clear — Clear recovery archive
- POST /api/recycle-source-dupes — Recycle original duplicate files from source folder (uses source_dupes.json mapping)
- POST /api/onedrive/status — Check if OneDrive is running and if a path is OneDrive-managed
- GET /api/app/state — Single source of truth: derive complete app state from filesystem
- POST /api/app/reset — Clear all in-memory progress dicts to prevent stale state

## Detailed Feature Descriptions

- Built-in file browser for staging and dupes folders with delete, folder delete, and Open in Explorer
- Dashboard shows folder browse buttons with file counts when staging/dupes have content
- Dashboard dynamic "Continue" button (label changes based on state: Continue to Scan/Review/Finalize/Finish Up) with "Choose a different step" stage picker dialog
- Dashboard "More Options" section: Send Files Home, Remove Workspace, Start Over, Rescue & Review, Move to Keepers, Delete All Remaining
- "Rescue & Review" loop: cycles dupes back through staging for iterative review, with merge or return/reload options. Merge has collision avoidance.
- "Start Over" consolidates all system folder files back into Staging for rescanning
- "Finish" view: summary page with file counts, multi-phase execution (restore kept files to source, recycle source duplicates, recycle workspace dupes, cleanup). Source duplicates are recycled via mapping saved at action time (scans/source_dupes.json).
- Persistent review decisions: auto-saved to scans/decisions_*.json, loaded on review init, resume where left off
- Chunked review: configurable batch size (50/100/250/500/All), checkpoint dialog at end of each batch
- Top menu: Dashboard | Migrate to Staging | Scan | Review | Finalize | Staging | Recovery | Keepers | Scan Logs | Settings | Help (greyed out when not applicable)
- SaddleCode company mark in nav bar upper-right (cursive Segoe Script, saddle tan #C19A6B)
- Status bar shows tooltips/hints enabled status with "Enable/Disable in Settings" link
- Finalize view includes Send Files Home button (single confirmation) as alternate path
- Finalize nav disabled when only staging has files (nothing to finalize)
- Scan nav goes directly to scan-config (skips wizard Step 1 when files exist)
- Rescan boxes on dashboard for Recovery and Keepers (greyed out if empty)
- Direct Scan: non-wizard scan path (renamed from Advanced Scan)
- Scan mode + threshold explanations on scan config pages
- "Remove Workspace" dialog: offers Send Files Home or Send to Recycle Bin (with confirmation)
- "Send Files Home" is a full refund: restores ALL system folder files (workspace, dupes, keepers) to source, cleans up silently
- Recycle Bin support: PowerShell-based with -ExecutionPolicy Bypass, falls back to permanent delete if PowerShell unavailable
- Keepers folder: third system folder for verified-good files promoted from dupes via "Move to Keepers" button
- Configurable scan batch size (checkpoint interval) via settings
- Chunked scanning: scan batch size dropdown (All/500/1000/2000/5000, default 2000). Scans first N files, after review+actions the next scan picks up remaining files.
- Auto-recycle exact duplicates: checkbox on scan config page. When enabled, byte-for-byte identical files are automatically sent to Recycle Bin (keeps largest). Zero false positives. Default: unchecked.
- Dashboard flow stepper: progress bar (Import > Scan > Review > Finish) with contextual hints
- Rolling recovery archive: 2-slot backup in PixHerder_Recovery folder. Before files are recycled, copies are preserved. 2 most recent operations kept.
- OneDrive sync management: auto-detects OneDrive process, pause-sync prompts, toggle in Settings (show_onedrive_prompts)
- Centralized state: getAppState() endpoint derives all app state from filesystem. No in-memory caches trusted.
- Folder picker: Browse button on wizard Step 1, opens at detected pictures path. Drive-level navigation.
- Unified hints bar: yellow bar at top of page with contextual flow hints + keyboard shortcuts
- Three display toggles in Settings: show_hints, show_tooltips, show_explanations. All default true, persistent.
- Four workflow modes: Easy (guided wizard), Autonomous (one-click auto-pipeline), Hybrid (wizard + dashboard, default/recommended), Manual (migration only, then dashboard).
- First-launch tour: 5-step slideshow (Welcome, How It Works, Modes, Safety, Ready). Skippable, replayable.
- Review UX: click images to toggle keep/dupe, multi-keep support, zoom button, action bar with Keep This Group/Mark as Duplicate/Delete Duplicate(s)/Mark All Remaining/Keep All Remaining/Apply Decisions/Exit
- Review metadata: image cards show dimensions, file size, date modified, and similarity percentage. Lightbox shows metadata overlay bar.
- Review bulk actions preserve previous picks (only affect unreviewed groups)
- No-dupes-found: scan completion shows Rescan/Done instead of empty review
- Blocking progress view (#working): all file operations navigate to a dedicated spinner page
- Navigation: navigate() forces route() refresh when hash unchanged
- Restart/refresh always lands on dashboard (stateful views redirect via _appNavigated flag)
- Consistent labeling: "Staging", "Recovery", "Keepers" everywhere
- Standardized dialog format: action buttons top-right, separator, explanations with white bold labels, Cancel bottom-left
- Standardized button colors by intent: green=safe/forward, red=destructive, amber=caution, gray=alternative
- Standardized button sizes: btn-fixed (160px) for actions, btn-browse (180px) for folders
- Duplicate destination choice: at finalize, user chooses Recycle Bin or PixHerder_Duplicates folder
- Dashboard stats show most recent scan only (not cumulative)
- Legacy scripts archived in archive/legacy_scripts/
- Test files archived in archive/test_files/
- Two independent audits completed (Auditor/ directory). Always verify audit claims against actual code.

## File Structure

```
TODO.md                    # Persistent task list
BUGS.md                    # Bug tracker
PROJECT_OVERVIEW.md        # What PixHerder does, who it's for, typical workflow
setup.bat                  # One-time setup: downloads Python, installs deps, generates launchers
pixherder_app.py          # Entry point — starts server, opens browser
engine/
  scanner.py               # Image discovery
  hasher.py                # MD5 and perceptual hashing
  comparator.py            # Duplicate grouping logic
  actions.py               # Move, delete, rescue operations
  oddball.py               # Oddball verification
  config.py                # Settings, paths, defaults (all dynamic)
  checkpoint.py            # Resumable scan checkpoints
  staging.py               # OneDrive staging (copy to local)
  dupe_folder.py           # Move dupes to user-visible folder (alternative to Recycle Bin)
web/
  server.py                # HTTP server, API routes, static file serving
  bridge.py                # pywebview API bridge — Python-JS bridge for native mode
  index.html               # SPA HTML structure (views only, no inline CSS/JS)
  style.css                # All CSS (dark theme, components, layout)
  app.js                   # Core JS: state, router, api, toast, dialog, utilities
  dashboard.js             # Dashboard view, folder status, More Options
  wizard.js                # 4-step wizard flow
  scan.js                  # Scan config + progress
  review.js                # Review + decisions + chunking
  browser.js               # File browser
  actions.js               # Action execution
  finish.js                # Finish flow
  staging.js               # Migration progress
  syncback.js              # Sync-back workflow
  working.js               # Blocking progress view
  modes.js                 # Workflow modes, mode selector, autonomous pipeline
  settings.js              # Settings view
  oddball.js               # Oddball verification
python/                    # Embedded Python runtime (created by setup.bat, gitignored)
scans/                     # Saved scan results (JSON)
logs/                      # Action logs + activity.log
checkpoints/               # Resumable scan state
PixHerder_Recovery/       # Rolling recovery archive (2-slot backup)
settings.json              # User preferences (auto-created on first use)
requirements.txt           # Python dependencies (Pillow, imagehash, pywebview)
archive/
  legacy_scripts/          # Original CLI tools
  test_files/              # Test scripts and debug output
```

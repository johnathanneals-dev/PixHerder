# DupeFinder TODO

Persistent task list tracked in the repo. Updated with every commit cycle.
See also: `Auditor/` for audit reports (Audit #1: Audit190326.txt, Audit #2: DupeFinder_Audit_Report*.txt)
Game plan: `.claude/plans/robust-weaving-thompson.md` for phased fix schedule.

---

## Audit Phase 1: Safety & Memory [COMPLETED 2026-03-20]

- [x] #1 Remove all os.remove() fallbacks for user files (staging.py, actions.py) -- leave files in place on Recycle Bin failure
- [x] #2 Fix Pillow Image leak in hasher.py -- use context manager for Image.open()
- [x] #3 Stream images + fix directory traversal in server.py _serve_image() -- path validation + shutil.copyfileobj
- [x] #24 Disk space check before migration -- warn if insufficient free space
- [x] #25 Manifest validation on restore -- integrity check before Send Files Home
- [x] #26 Clean up decision files (scans/decisions_*.json) on scan delete
- [x] #29 Add /api/staging/reset endpoint -- replace "cleared" path hack in finish flow

## Audit #2: Verified Fixes [COMPLETED 2026-03-20]

- [x] Fix use_fallback NameError in recycle_staging() return dict (crash on every recycle)
- [x] Fix indentation error in _handle_staging_status (staging recovery broken)
- [x] Remove os.remove() fallback in _handle_browser_delete (last permanent delete path)
- [x] Remove CORS wildcard header from scan progress SSE
- [x] Disable heartbeat auto-shutdown in native pywebview mode

## Audit #2: Before Release [COMPLETED 2026-03-20]

- [x] Replace os._exit(0) with graceful server.shutdown() (3 locations)
- [x] Restrict /api/browse-folders to block system directories
- [x] Consolidate extension lists to single IMAGE_EXTENSIONS in config.py
- [x] Add copy verification (size check) before deleting source files
- [x] Track/limit progress polling threads in bridge.py
- [x] Validate settings paths -- reject system directories
- [x] Add session token for browser-mode CSRF protection

## Audit Phase 2: Performance & Quality [NEXT]

- [x] #4 Batch PowerShell recycling -- _recycle_files_batch_powershell() added
- [x] #5 Move defaults from temp to LOCALAPPDATA -- DupeFinder subfolder under LOCALAPPDATA
- [x] #7 Add view teardown to SPA router -- implemented in stale data fix (route() clears state on view change)
- [x] #8 Extract shared _is_allowed_path() helper in server.py (5 locations consolidated)
- [x] #9 Fix move counter -- fixed verify_copy error handling (wrong variable names)
- [x] #27 Auto-shutdown race -- removed (no auto-shutdown in native mode)
- [x] #28 Server restart -- removed (no restart in native mode, close window to exit)

## Audit Phase 3: Algorithmic (When Scaling)

- [x] #6 O(n^2) perceptual comparison -- addressed with LSH multi-band bucketing (20% speedup)
- [x] #13 Union-Find for perceptual clustering -- replaces greedy adjacency in LSH branch
- [x] #10 Scanner follows symlinks -- fixed with os.walk(followlinks=False) + is_symlink checks
- [x] #14 Thread-safe progress dicts -- documented GIL + dict copy pattern as sufficient

## Audit Phase 4: Polish

- [x] #11 Add /api/staging/reset endpoint (replaced fake restore hack in finish.js) -- done in Phase 1
- [x] #12 Better error reporting in Return/Reload -- catch handlers on all RnR promise chains
- [ ] #15 Accessibility -- ARIA labels, focus trapping, keyboard nav
- [x] #17 Fix duplicate style attributes in HTML (scanKeepersSection, finishKeepersRow merged)
- [x] #18 Improve OneDrive detection -- checks OneDrive/OneDriveConsumer/OneDriveCommercial env vars
- [x] #19 Populate oddball errors list -- hash failures now tracked
- [x] #20 Replace innerHTML += with insertAdjacentHTML in browser.js
- [x] #21 Add timeout to working view (120s with escape button)
- [x] #22 Incremental checkpoint writes -- already uses atomic temp+replace pattern
- [x] #23 Dynamic port in status bar from settings

## Feature Backlog (from testing session)

- [x] Sticky browser toolbar: buttons stay at top when scrolling in folder view (fixed: moved to nav bar row)
- [x] Persistent logging toggle -- badge visibility fixed with retry on startup
- [x] Debug mode toggle (Ctrl+Shift+F7) -- implemented, reads from settings on startup
- [ ] Auto-move duplicates to Removed Duplicates option (scan moves dupes automatically, user reviews after)
- [x] Tooltips on Execute Actions view (batch dialog is known limitation — z-index overlap)
- [x] BUG: "Rescan" from scan results -- fixed to navigate to scan-config directly
- [x] BUG: "Complete migration first" toast -- caused by Rescan going through wizard, fixed
- [x] BUG: Send Files Home -- fixed bridge staging_status to read source_dir from manifest
- [x] BUG: Recovery archive browse -- improved error message, edge case when archive empty
- [x] BUG: Duplicate files in review -- exact dupes removed from perceptual scan input
- [x] Standardize scan windows -- wizard Step 2 already has Return to Dashboard
- [x] Batch complete dialog: Cancel left, Next Batch + Take a Break right
- [x] Clear archive shows confirmation dialog with OK button
- [x] Help link in nav menu (placeholder view added)
- [ ] "Choose another destination" option for Send Files Home
- [ ] Audit all navigation: ensure buttons everywhere except top menu text links
- [ ] Recycle Bin capacity indicator before bulk recycle operations
- [ ] "Delete All Remaining" button accessible from review process
- [ ] My Files browser: add "Move to Keepers" and "Move to Be Reviewed" buttons
- [ ] Move to Keepers: let user choose My Files, Removed Duplicates, or both as source
- [ ] Multiple source folder support (import from several directories)
- [ ] Keepers folder workflow -- rescan Removed Duplicates, promote to Verified Keepers
- [x] Batch/chunked scanning for large collections
- [x] **pywebview migration** -- native window replaces browser (completed 2026-03-20)
- [ ] Server modularization -- split server.py into route modules (partially addressed by pywebview migration)
- [ ] Marketability -- branding, installer, landing page, packaging
- [ ] Thumb drive portable mode -- running from USB with virtual environment
- [ ] Additional keyboard shortcuts (E=execute, F=finish, Space=lightbox, 1-9=jump to group)
- [ ] Numbered menu items matching wizard step numbers
- [ ] File Safety / Expert mode toggle (reduces dialog count for experienced users)
- [x] Dashboard stats: show cumulative totals across all scans
- [x] "Continue to Finalize" renamed to "Access Wizard Steps"
- [x] Wizard steps clickable when conditions met (active step now clickable too)
- [ ] OneDrive sync management: pause-sync prompts before bulk operations
- [ ] OneDrive "Keep or Delete" dialog: advance explanation of what to choose
- [ ] Auto-detecting OneDrive sync state before bulk operations
- [ ] Built-in #help view with anchored topics replacing verbose UI text
- [ ] Help section: full nav + "Back to where I was" button
- [ ] Testing data tracking doc for consistency across test sessions

## Completed (2026-03-21)

- [x] Auto-recycle exact duplicates: checkbox on scan config, byte-for-byte identical files automatically sent to Recycle Bin (keeps largest), zero false positives, default unchecked
- [x] Smart dashboard flow guidance: progress stepper (Import > Scan > Review > Finish) with contextual hints showing workflow position and next action
- [x] Rolling recovery archive: 2-slot backup in DupeFinder_Recovery folder, copies preserved before recycling, browse/restore from dashboard, cleared on session finish
- [x] Chunked scanning: scan batch size dropdown (All/500/1000/2000/5000, default 2000), scans first N files, next scan picks up remaining after review+actions

## Completed (2026-03-20)

- [x] Phase 1 safety fixes: removed all os.remove() fallbacks, fixed Image leak, directory traversal fix, streaming images, disk space check, manifest validation, decision cleanup, /api/staging/reset endpoint
- [x] pywebview migration: native window, bridge.py (45 API methods + 5 progress subscriptions), SSE replaced with evaluate_js callbacks, legacy --browser mode preserved
- [x] Audit #2 immediate fixes: use_fallback crash, indentation bug, browser_delete fallback, CORS removal, heartbeat disable in native mode
- [x] Archive legacy scripts and test files to archive/ directory
- [x] PROJECT_OVERVIEW.md for auditor context
- [x] Audit #2 before-release: graceful shutdown, browse-folders restriction, extension consolidation, copy verification, thread tracking, settings validation, CSRF token

## Completed (2026-03-19)

- [x] Frontend modularization -- index.html split into 15 files (style.css + 13 JS modules + HTML)
- [x] Fix finish flow -- replaced destructive sync-back with safe restore (never deletes originals)
- [x] Chunked review with persistent decisions and auto-save
- [x] Top menu redesign: Dashboard | Migrate | Scan | Review | Finalize | Activity | Settings
- [x] Grey out nav items when not applicable
- [x] Rename Advanced Scan to Direct Scan
- [x] Rescan boxes on dashboard (Removed Duplicates + Verified Keepers)
- [x] Fix "Choose a different step" button missing border
- [x] Post-action navigation: horizontal stage buttons + Open Recycle Bin
- [x] Perceptual threshold + scan mode explanations on scan config
- [x] Return to Dashboard button on scan config and wizard Step 3
- [x] Toast improvements: warning/error toasts blink and stay longer
- [x] Rename Keep All to Keep This Group, Delete to Delete Duplicate(s)
- [x] Fix staging folder discovery bug (_find_staging_subfolder helper)
- [x] Fix inflated file counts in execute actions with Both scan mode
- [x] Fix wizard skipping to Stage 4 after Send Files Home
- [x] Rename Cleaned Files to My Files throughout
- [x] Fix Explorer and Recycle Bin opening behind browser (window.blur)
- [x] Remove duplicate Back to Dashboard button from action results
- [x] Blocking progress view (#working) for all file operations
- [x] File safety documentation expanded
- [x] Design standards document (DESIGN_STANDARDS.md)
- [x] TODO.md persistent task tracker
- [x] Independent audit completed (28 issues identified)

## Future Vision (separate apps / major features)

- [ ] Face detection/recognition in photos (may warrant separate app)
- [ ] Duplicate video finder (separate app — different algorithms, larger files)
- [ ] Unified dashboard app to manage all tools (DupeFinder, video deduper, face finder, etc.)

## Won't Do / Deferred

- IE11/Edge Legacy support (document only, no polyfills)
- Windows 8.1 support (Windows 10 1803+ is minimum)

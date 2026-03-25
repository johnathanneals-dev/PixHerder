# PixHerder TODO

Persistent task list tracked in the repo. Updated with every commit cycle.
See also: `Auditor/` for audit reports (Audit #1: Audit190326.txt, Audit #2: PixHerder_Audit_Report*.txt)
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
- [x] #5 Move defaults from temp to LOCALAPPDATA -- PixHerder subfolder under LOCALAPPDATA
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
- [x] #15 Accessibility -- ARIA labels added to dialog, lightbox, toast, nav, main, status bar (focus trapping deferred)
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
- [ ] Auto-move duplicates to Recovery option (scan moves dupes automatically, user reviews after)
- [x] Tooltips on Execute Actions view (batch dialog is known limitation — z-index overlap)
- [x] BUG: "Rescan" from scan results -- fixed to navigate to scan-config directly
- [x] BUG: "Complete migration first" toast -- caused by Rescan going through wizard, fixed
- [x] BUG: Folder picker browsed to wrong Pictures folder (local vs OneDrive) -- fixed: default to detected path, drive-level navigation, post-selection image count toast
- [x] BUG: Start Over fails after Send Files Home -- state validator cleaned up staging folder, consolidate now creates one
- [x] BUG: Keyboard shortcuts bar overlaps nav menu -- moved to unified yellow hints bar at top
- [x] Unified hints bar: yellow bar at top with flow hints + keyboard shortcuts (review only) + settings note
- [x] Title bar / nav bar split: logo row separate from nav links row
- [x] Show explanation text toggle: new show_explanations setting in Settings
- [x] Button color standard applied across all views
- [x] BUG: Send Files Home -- fixed bridge staging_status to read source_dir from manifest
- [x] BUG: Recovery archive browse -- improved error message, edge case when archive empty
- [x] BUG: Duplicate files in review -- exact dupes removed from perceptual scan input
- [x] Standardize scan windows -- wizard Step 2 already has Return to Dashboard
- [x] Batch complete dialog: Cancel left, Next Batch + Take a Break right
- [x] Clear archive shows confirmation dialog with OK button
- [x] Help link in nav menu (placeholder view added)

### Priority 1: Fix Now

- [ ] **Easy mode routing** -- Easy mode lands on blank dashboard instead of wizard. The fresh-load redirect in route() doesn't trigger because the default hash resolves to "dashboard" before the redirect logic runs. Need to detect Easy mode in route() and redirect to wizard view on load. Files: web/app.js route() function.

### Priority 1b: Finalize Flow Fixes

- [ ] **Finalize warning for clean Recovery files** -- Before recycling Recovery, check if the most recent scan of Recovery found 0 duplicate groups. If so, show warning dialog: "Recovery has X files that weren't found as duplicates. These may be keepers. Send them home instead of recycling?" Options: Send Home (green), Recycle Anyway (red), Cancel. Prevents accidental loss of reviewed survivors. Files: web/finish.js _executeFinish(), needs scan history check.

- [ ] **Auto-promote after clean Recovery scan** -- When scanning Recovery returns 0 groups, show dialog on the scan complete screen: "No duplicates found. These X files appear to be keepers. Move them to Keepers?" Options: Move to Keepers (green), Leave in Recovery (amber), Send Home (green). This gives the user an immediate exit instead of leaving clean files stranded in Recovery. Files: web/scan.js showScanComplete(), needs folder context check.

- [ ] **Finalize view title/description rewrite** -- "Finalize" is vague. Keep button labels short but make the view title and description explicit about what will happen. Title: "Send Files Home & Clean Up" or similar. Description should clearly state: "Your kept files will be copied back to [source]. Files in Recovery will be sent to the Recycle Bin. Your originals are never deleted." Files: web/finish.js, web/index.html finish view.

- [ ] **Finish progress bar race condition** -- Progress bar shows 0% until completion. Subscription now starts before restore API call (fix applied this session) but needs testing with a real file set to verify. Files: web/finish.js.

### Priority 2: Safety & Protection

- [ ] **Path safety guards** -- 3 tiers: (1) Hard block C:\Windows with dialog explaining why and suggesting File Explorer to manually extract images. (2) Warning dialog for Program Files and any drive root (C:\, E:\, USB volumes) showing image count, user decides. (3) Everything else proceeds normally. Add `is_safe_source_path()` to engine/config.py. Apply in web/bridge.py staging_start(), web/server.py _handle_staging_start(), web/wizard.js, web/modes.js autonomous pipeline.

### Priority 3: Enhanced Mode

- [ ] **Enhanced Mode** -- Opt-in checkbox in Settings: "Enable Enhanced Mode" with a ? button next to it (tooltip: "Explanation", links to help manual section). When checked, navigates to walkthrough screen with editable fields for CPU cores, RAM (GB), disk space (GB). "Auto-detect" button fills fields automatically (use ctypes kernel32 GlobalMemoryStatusEx for RAM, os.cpu_count(), shutil.disk_usage() -- no external deps). User can manually enter values instead (avoids antivirus concerns). "Save for Enhancement" applies profile and adjusts recommended scan batch. Profile stored in settings.json as system_profile: { cores, ram_gb, disk_free_gb, recommended_batch }. Recommendation formula: RAM <4GB=2000, 4-8GB=5000, 8-16GB=7500, 16GB+=10000. Advisory only -- user picks from dropdown, recommendation highlighted. Leave decent resource buffer so PixHerder never hogs the system. Cancel unchecks box and returns to Settings. Back to Dashboard unchecks box and returns to dashboard. Later unchecking shows "Revert to default settings?" confirmation. Help manual section needed: thorough explanation of what Enhanced Mode does, what to expect enabling/disabling, methodology. Files: engine/config.py, web/index.html, web/settings.js, web/modes.js, USERS_MANUAL.md.

### Priority 4: Migration & Workflow

- [ ] **Migration manifest for large folders** -- Track source file paths already copied in a manifest alongside the staging manifest. Repeat migrations skip files already in the list. Filesystem fallback if manifest lost (check if file exists at destination). Enables processing folders with more files than one session's worth without duplicating work. No hard cap on migration size -- migration is I/O bound, not resource intensive.
- [ ] **Power loop workflow** -- "Move All to Recovery" button on scan results page (skip review). Enables fast winnowing loop: scan > bulk-move dupes > rescan > repeat until clean > promote staging to Keepers > move Recovery back to staging > detailed review on concentrated dupes.
- [x] **Scan batch dropdown update** -- Options: 500/1000/2000/5000/7500/10000 (removed "All" to avoid resource exhaustion). Default: 2000.
- [x] **Finalize button on scan complete** -- Green "Finalize" button on scan complete card, only visible when Recovery or Keepers have files.
- [ ] **Scan from Recovery review** -- Currently clicking Recovery opens file browser only. User should be able to trigger review from Recovery browser directly (scan + review in one flow). For now, "Scan Recovery" on dashboard handles this.

### Priority 5: Polish & Features

- [x] EXIF metadata in review: dimensions, file size, date modified, similarity % on image cards + lightbox overlay
- [x] 4 workflow modes: Easy (guided), Autonomous (one-click), Hybrid (recommended), Manual (power user). Mode selector on first launch, changeable in Settings. Locked for this version -- no additional modes.
- [ ] Restart button: green button in status bar bottom-left, shifts server info toward middle. Tooltip, small confirmation dialog, force-closes and relaunches app with no further interaction.
- [ ] Double-launch protection: second instance via shortcut leaves orphaned pythonw.exe process. Current single-instance check (port bind) exits silently but process may linger. Investigate mutex or PID file approach.
- [ ] Wizard walkthrough: thorough end-to-end review of the 4-step wizard flow, verify all states and transitions
- [ ] Auto-move duplicates option: scan identifies and moves dupes to Recovery automatically, user reviews after
- [ ] "Choose another destination" option for Send Files Home
- [ ] Recycle Bin capacity indicator before bulk recycle operations
- [ ] Browser file management: "Move to Keepers" and "Move to Be Reviewed" buttons in Staging browser
- [ ] Move to Keepers source picker: choose Staging, Recovery, or both
- [ ] Multiple source folder support (import from several directories)
- [ ] Verbose text toggle: checkbox in settings to control wizard explanation verbosity. When unchecked, minimal text describing function only. Separate from hints toggle.
- [ ] Adaptive resolution: detect screen resolution on startup, define display profiles (full/compact/minimal), adjust layouts per profile. Extend existing CSS breakpoints (1024/768/480). Toast warning if below 1280x720.
- [ ] Expert mode toggle (reduces dialog count for experienced users)

### Code Quality (Pike's Rules Audit -- 2026-03-24)

- [ ] Unify server.py progress globals -- 6 identical dicts into one dict-of-dicts. Cuts ~50 lines. Rule 5 violation. HIGH BLAST RADIUS: bridge.py imports all 6 by name, plus every runner function references them directly. Do in a fresh session with full testing.
- [ ] Extract inline styles from index.html to CSS classes -- 100+ inline style attributes. Biggest single frontend issue. Rule 5.
- [ ] Refactor dialog building -- Replace inline HTML string generation in app.js, review.js, finish.js with template helpers or data-driven builders. Rule 5.
- [ ] Split _dashUpdateFlowGuide() -- 70-line function doing 4 things (step states, stepper HTML, hint text, continue logic). Should be 3-4 functions. Rule 4.
- [ ] Data-drive scan context configs -- Replace if/else chains in scan.js initScanConfig() with a context config object. Rule 4.
- [ ] Data-drive wizard step init -- Replace 4 if-branches in wizardGoToStep() with a step handler map. Rule 4.
- [ ] Evaluate LSH threshold -- comparator.py uses 500-file threshold for LSH bucketing. Unmeasured. Either measure it or document why 500. Rule 1.
- [ ] Collapse hybrid/manual mode nav configs -- Identical in modes.js. Rule 4.
- [ ] Server modularization -- split server.py into route modules

### OneDrive Integration

- [x] OneDrive sync management: pause-sync prompts, "Keep or Delete" explanation, auto-detect sync state

### Help System

- [ ] Built-in #help view: render USERS_MANUAL.md content in-app with search box, topic anchors, full nav, "Back to where I was" (placeholder view exists)

### Testing

- [ ] USB drive: plug in a USB drive, verify folder picker shows it in My Computer view, migrate files from it, send files back to it

### Distribution

- [ ] Marketability -- branding, installer, landing page, packaging
- [ ] Thumb drive portable mode -- running from USB with virtual environment

### Previously Completed

- [x] Audit all navigation: top nav text links by design, all other nav uses buttons
- [x] "Delete All Remaining" accessible from review (Recycle All Remaining button)
- [x] Batch/chunked scanning for large collections
- [x] pywebview migration -- native window replaces browser
- [x] Additional keyboard shortcuts (E=apply, Space=lightbox, Escape=close)
- [x] Numbered menu items -- addressed by flow stepper
- [x] Dashboard stats: cumulative totals across all scans
- [x] "Continue to Finalize" renamed to "Access Wizard Steps"
- [x] Wizard steps clickable when conditions met

## Completed (2026-03-21)

- [x] Auto-recycle exact duplicates: checkbox on scan config, byte-for-byte identical files automatically sent to Recycle Bin (keeps largest), zero false positives, default unchecked
- [x] Smart dashboard flow guidance: progress stepper (Import > Scan > Review > Finish) with contextual hints showing workflow position and next action
- [x] Rolling recovery archive: 2-slot backup in PixHerder_Recovery folder, copies preserved before recycling, browse/restore from dashboard, cleared on session finish
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
- [x] Rescan boxes on dashboard (Recovery + Keepers)
- [x] Fix "Choose a different step" button missing border
- [x] Post-action navigation: horizontal stage buttons + Open Recycle Bin
- [x] Perceptual threshold + scan mode explanations on scan config
- [x] Return to Dashboard button on scan config and wizard Step 3
- [x] Toast improvements: warning/error toasts blink and stay longer
- [x] Rename Keep All to Keep This Group, Delete to Delete Duplicate(s)
- [x] Fix staging folder discovery bug (_find_staging_subfolder helper)
- [x] Fix inflated file counts in execute actions with Both scan mode
- [x] Fix wizard skipping to Stage 4 after Send Files Home
- [x] Rename Cleaned Files to Staging throughout
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
- [ ] Unified dashboard app to manage all tools (PixHerder, video deduper, face finder, etc.)

## Won't Do / Deferred

- IE11/Edge Legacy support (document only, no polyfills)
- Windows 8.1 support (Windows 10 1803+ is minimum)

# DupeFinder TODO

Persistent task list tracked in the repo. Updated with every commit cycle.
See also: `Auditor/Audit190326.txt` for the full independent audit report.
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

## Audit Phase 2: Performance & Quality [NEXT]

- [ ] #4 Batch PowerShell recycling -- single invocation for all files instead of per-file spawning
- [ ] #5 Move defaults from temp to LOCALAPPDATA -- prevent Storage Sense from deleting staged files
- [ ] #7 Add view teardown to SPA router -- close SSE/observers on view exit
- [ ] #8 Extract shared _check_allowed_path() helper in server.py (4 duplicated locations)
- [ ] #9 Fix move counter -- increment after BOTH copy2 and os.remove succeed
- [ ] #27 Auto-shutdown race -- suppress during long API calls
- [ ] #28 Server restart os.execv() hangs -- need robust restart mechanism

## Audit Phase 3: Algorithmic (When Scaling)

- [ ] #6 O(n^2) perceptual comparison -- BK-tree or bucket-by-prefix for 10K+ images
- [ ] #13 Union-Find for perceptual clustering -- consistent groups regardless of file order
- [ ] #10 Scanner follows symlinks -- use os.walk(followlinks=False)
- [ ] #14 Thread-safe progress dicts -- add threading.Lock per dict

## Audit Phase 4: Polish

- [x] #11 Add /api/staging/reset endpoint (replaced fake restore hack in finish.js) -- done in Phase 1
- [ ] #12 Better error reporting in Return/Reload 3-step API chain
- [ ] #15 Accessibility -- ARIA labels, focus trapping, keyboard nav
- [ ] #17 Fix duplicate style attributes in HTML (scanKeepersSection, finishKeepersRow)
- [ ] #18 Improve OneDrive detection (env var / registry instead of string check)
- [ ] #19 Populate oddball errors list (currently dead code)
- [ ] #20 Replace innerHTML += with insertAdjacentHTML in browser.js
- [ ] #21 Add timeout to working view (60s fallback with escape button)
- [ ] #22 Incremental checkpoint writes for large scans
- [ ] #23 Dynamic port in status bar from settings

## Feature Backlog (from testing session)

- [ ] "Choose another destination" option for Send Files Home
- [ ] Audit all navigation: ensure buttons everywhere except top menu text links
- [ ] Recycle Bin capacity indicator before bulk recycle operations
- [ ] "Delete All Remaining" button accessible from review process
- [ ] My Files browser: add "Move to Keepers" and "Move to Be Reviewed" buttons
- [ ] Move to Keepers: let user choose My Files, Removed Duplicates, or both as source
- [ ] Multiple source folder support (import from several directories)
- [ ] Keepers folder workflow -- rescan Removed Duplicates, promote to Verified Keepers
- [ ] Batch/chunked scanning for large collections
- [ ] Server modularization -- split server.py into route modules
- [ ] Marketability -- branding, installer, landing page, packaging
- [ ] Thumb drive portable mode -- running from USB with virtual environment
- [ ] Additional keyboard shortcuts (E=execute, F=finish, Space=lightbox, 1-9=jump to group)
- [ ] Numbered menu items matching wizard step numbers
- [ ] File Safety / Expert mode toggle (reduces dialog count for experienced users)
- [ ] Dashboard stats: show cumulative session totals instead of zeros
- [ ] "Continue to Finalize" rename to "Access Wizard Steps"
- [ ] Wizard steps should stay accessible/clickable when conditions are met
- [ ] OneDrive sync management: pause-sync prompts before bulk operations
- [ ] OneDrive "Keep or Delete" dialog: advance explanation of what to choose
- [ ] Auto-detecting OneDrive sync state before bulk operations
- [ ] Built-in #help view with anchored topics replacing verbose UI text
- [ ] Help section: full nav + "Back to where I was" button
- [ ] Testing data tracking doc for consistency across test sessions

## Completed (2026-03-20)

- [x] Phase 1 safety fixes: removed all os.remove() fallbacks, fixed Image leak, directory traversal fix, streaming images, disk space check, manifest validation, decision cleanup, /api/staging/reset endpoint

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

## Won't Do / Deferred

- IE11/Edge Legacy support (document only, no polyfills)
- Windows 8.1 support (Windows 10 1803+ is minimum)

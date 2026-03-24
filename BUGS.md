# PixHerder Bug Tracker

Comprehensive record of all bugs found and fixed. Updated with every commit cycle.

---

## Active Bugs

None currently known.

## Fixed This Session (2026-03-23 evening, second commit)

**Start Over fails with "Unknown error"**
- **Found:** Testing, 2026-03-23
- **Description:** State validator cleaned up empty staging folder and manifest after Send Files Home. `consolidate()` then failed because `_find_staging_subfolder()` returned empty. Also, response used `status` key but frontend checked `success`.
- **Fix:** `consolidate()` creates a new staging subfolder when none exists. Fixed response key to `success: true`.
- **Files:** web/bridge.py

**Finish progress bar stuck at 0%**
- **Found:** Testing, 2026-03-23
- **Description:** Finish restore phase was synchronous -- copied all files in a blocking loop with no progress updates. Progress bar sat at 0% until completion. With 6K+ files, user nearly killed the process thinking it stalled.
- **Fix:** Restore now runs in a background thread (`_run_restore` in server.py) with progress dict updates. Frontend subscribes via `subscribe_restore_progress` and updates the bar in real-time.
- **Files:** web/bridge.py, web/server.py, web/finish.js

**Keyboard shortcuts bar overlaps nav menu**
- **Found:** Testing, 2026-03-23
- **Description:** kbd-hints was a flex child inside the topnav, competing for space with nav links. On narrow windows or when nav wrapped to two rows, shortcuts covered navigation buttons.
- **Fix:** Moved to unified yellow hints bar at the very top of the page, above a new separate title bar. Nav links in their own row below.
- **Files:** web/index.html, web/style.css, web/app.js

---

## Fixed Bugs

### Critical (Crash/Security)

**use_fallback NameError crash on every recycle operation**
- **Found:** Audit #2, 2026-03-20
- **Commit:** 2d70dc6
- **Description:** `recycle_staging()` return dict referenced undefined `use_fallback` variable. Every successful recycle operation crashed.
- **Fix:** Corrected variable name in return dict.
- **Files:** web/bridge.py

**Finish flow permanently deletes originals from source**
- **Found:** Testing, 2026-03-19
- **Commit:** b2f5285
- **Description:** Finish flow called `sync_back_deletions()` which used `os.remove()` to permanently delete original files from the OneDrive source folder. Users lost original files with no recovery path.
- **Fix:** Replaced destructive sync-back with safe restore operation. Finish now copies kept files back to source and recycles dupes. Originals are never touched.
- **Files:** engine/staging.py, web/finish.js

**Directory traversal in image serving endpoint**
- **Found:** Audit #1, 2026-03-20
- **Commit:** 49aa462
- **Description:** `_serve_image()` had no path validation. Attacker could request any file on disk via crafted path parameter.
- **Fix:** Added path validation against allowed directories (staging, dupes, keepers, source). Returns 403 for unauthorized paths.
- **Files:** web/server.py

**Pillow Image file handle leak**
- **Found:** Audit #1, 2026-03-20
- **Commit:** 49aa462
- **Description:** `Image.open()` in hasher.py not using context manager. On large scans, file handles exhausted causing crashes.
- **Fix:** Wrapped all `Image.open()` calls in `with` context managers.
- **Files:** engine/hasher.py

**ALL dialogs broken in review/finalize**
- **Found:** Testing, 2026-03-22
- **Commit:** 8460873
- **Description:** `showDialog()` CSS selector referenced `btn-secondary` but Cancel buttons had been changed to `btn-ghost`. Every multi-option dialog was invisible/non-functional.
- **Fix:** Updated selector from `btn-secondary` to `btn-ghost`.
- **Files:** web/app.js

**Indentation error breaks staging recovery**
- **Found:** Audit #2, 2026-03-20
- **Commit:** 2d70dc6
- **Description:** `_handle_staging_status()` had Python indentation error. Staging session recovery after app restart was completely broken.
- **Fix:** Corrected indentation.
- **Files:** web/bridge.py

---

### High Priority (Functionality)

**Folder picker browses to wrong Pictures folder**
- **Found:** Testing, 2026-03-23
- **Commit:** (this session)
- **Description:** Browse dialog started at USERPROFILE and showed local `Pictures` folder. On OneDrive systems, actual photos are at `OneDrive\Pictures`. Users selected the empty local folder, migration found 0 files every time. Activity log showed dozens of 0-file staging attempts.
- **Fix:** Default browse to `default_pictures_path()` (OneDrive\Pictures when detected). Added drive-level navigation (My Computer view) so users can reach any drive. Added post-selection image count toast for immediate feedback.
- **Files:** web/app.js, web/bridge.py, web/server.py

**Send Files Home fails -- source_dir not found**
- **Found:** Testing, 2026-03-22
- **Commit:** 4ed0a9f, e577744
- **Description:** Bridge `staging_status` read `source_dir` from `default_pictures_path()` instead of the manifest file. If the staging was created from a different source folder, Send Files Home failed with "Source folder not found."
- **Fix:** Read `source_dir` from manifest file first, fall back to default only if manifest missing.
- **Files:** web/bridge.py

**Stale dashboard after navigation**
- **Found:** Testing, 2026-03-19
- **Commit:** 90ab993
- **Description:** Hash-based SPA routing didn't refresh when navigating to the same route twice (e.g., dashboard > wizard > dashboard). Dashboard showed stale data.
- **Fix:** `navigate()` forces `route()` refresh when hash is unchanged.
- **Files:** web/app.js

**Wizard skips Step 1 on cold start**
- **Found:** Testing, 2026-03-19
- **Commit:** b668fc4, 2d504bf, 8e9e177
- **Description:** Wizard skipped Step 1 if staging folder existed but was empty or had no image files. Fresh installs jumped to Step 2.
- **Fix:** Check both folder existence AND image file count before reporting valid session.
- **Files:** web/bridge.py, engine/staging.py

**Wizard skips to Stage 4 after Send Files Home**
- **Found:** Testing, 2026-03-19
- **Commit:** a25d9d8
- **Description:** Stale `staging_progress` dict caused wizard to detect a false session after Send Files Home completed.
- **Fix:** Clear progress dict when `full_restore` completes.
- **Files:** web/bridge.py

**Inflated file counts with Both scan mode**
- **Found:** Testing, 2026-03-19
- **Commit:** 2da828b
- **Description:** Both mode (MD5 + perceptual) showed same file in multiple groups. File counts in execute actions were inflated.
- **Fix:** Deduplicate file paths before counting and executing.
- **Files:** web/review.js, engine/actions.py

**Duplicate exact dupes appear in perceptual results**
- **Found:** Testing, 2026-03-22
- **Commit:** 3a05214
- **Description:** Files already matched as exact duplicates appeared again in perceptual groups.
- **Fix:** Remove exact-match paths from perceptual scan input.
- **Files:** engine/comparator.py

**Persistent logging lost on settings save**
- **Found:** Testing, 2026-03-23
- **Commit:** 50ea1c5
- **Description:** `saveSettings()` didn't preserve `persistent_logging` and `debug_mode` flags. Saving any setting reset both to false.
- **Fix:** Read current values before save and preserve them.
- **Files:** web/settings.js

**Persistent logging badge not showing on startup**
- **Found:** Testing, 2026-03-23
- **Commit:** 9ac3b8a
- **Description:** Badge update chained to `api/logs/enable` promise which could fail silently. Badge never appeared despite logging being active.
- **Fix:** Show badge immediately from settings value, with retry on startup.
- **Files:** web/app.js

**Folder browser shows [object Object]**
- **Found:** Testing, 2026-03-23
- **Commit:** e577744
- **Description:** Bridge browse response returned objects instead of strings. Response format mismatch between bridge and server implementations.
- **Fix:** Aligned bridge response format with server (entries, path, has_more).
- **Files:** web/bridge.py, web/server.py

**RnR merge silently fails on all files**
- **Found:** Testing, 2026-03-19
- **Commit:** 51246c7
- **Description:** Rescue & Review merge failed because files in Recovery already existed in Staging. `os.rename` fails on Windows when target exists.
- **Fix:** Added collision-avoidance with incrementing suffixes (e.g., `photo_1.jpg`).
- **Files:** engine/actions.py

**Scan batch size always defaults to 2000**
- **Found:** Testing, 2026-03-21
- **Commit:** 22698b1, a902681, 3055248, 3861767
- **Description:** Multiple related issues: missing int conversion, dropdown not initialized, resume check not respecting user-selected batch size.
- **Fix:** Force int conversion, explicit dropdown init, debug logging, pass scanLimit in catch path.
- **Files:** web/scan.js

---

### Security Fixes

**os.remove() fallback permanently deletes user files**
- **Found:** Audit #1, 2026-03-20
- **Commit:** 49aa462, 2d70dc6
- **Description:** When Recycle Bin failed, staging.py and actions.py fell back to `os.remove()` -- permanent deletion with no recovery.
- **Fix:** Removed all `os.remove()` fallbacks. Files left in place on Recycle Bin failure.
- **Files:** engine/staging.py, engine/actions.py, web/server.py

**CORS wildcard on SSE endpoint**
- **Found:** Audit #2, 2026-03-20
- **Commit:** 2d70dc6
- **Description:** Scan progress SSE had `Access-Control-Allow-Origin: *` header.
- **Fix:** Removed header. SSE only used in native mode anyway.
- **Files:** web/server.py

**Browse-folders allows system directory traversal**
- **Found:** Audit #2, 2026-03-20
- **Commit:** 013de85
- **Description:** `/api/browse-folders` could navigate to Windows, System32, Program Files.
- **Fix:** Blocked system directories with allowlist check.
- **Files:** web/server.py

**No copy verification before deleting source**
- **Found:** Audit #2, 2026-03-20
- **Commit:** 013de85
- **Description:** Move operations assumed copy success without verifying file size.
- **Fix:** Added size verification after copy, before deleting source.
- **Files:** engine/actions.py

**Settings paths accept system directories**
- **Found:** Audit #2, 2026-03-20
- **Commit:** 013de85
- **Description:** Custom settings paths could point to system directories.
- **Fix:** Validate paths against system directory blocklist.
- **Files:** engine/config.py

**No CSRF protection in browser mode**
- **Found:** Audit #2, 2026-03-20
- **Commit:** 013de85
- **Description:** No session token for browser-mode requests.
- **Fix:** Added CSRF session token. Not needed in native pywebview mode.
- **Files:** web/server.py

**os._exit(0) ungraceful shutdown**
- **Found:** Audit #2, 2026-03-20
- **Commit:** 013de85
- **Description:** Hard exit without cleanup in 3 locations.
- **Fix:** Replaced with `server.shutdown()` for graceful cleanup.
- **Files:** pixherder_app.py, web/server.py, web/bridge.py

**Read-only files not cleared before delete**
- **Found:** Testing, 2026-03-18
- **Commit:** 2ffc87c
- **Description:** OneDrive files inherit read-only attributes during sync. Delete operations failed silently.
- **Fix:** Clear read-only with `os.chmod()` before `os.remove()`.
- **Files:** engine/actions.py

---

### Medium Priority (UX/Data)

**Tooltip blocks button clicks**
- **Found:** Testing, 2026-03-21
- **Commit:** ffdfa11, bf718a9, 01508f5, 6922ef5
- **Description:** Tooltip modal intercepted mouse events, preventing action button clicks.
- **Fix:** Series of fixes: hide on click, hide on mousedown, pointer-events:none on tooltip body.
- **Files:** web/style.css, web/app.js

**Scanner follows symlinks causing infinite loops**
- **Found:** Audit Phase 3, 2026-03-22
- **Commit:** a461d69
- **Description:** `os.walk()` default follows symlinks. Circular links caused infinite scanning.
- **Fix:** `os.walk(followlinks=False)` and `is_symlink` checks.
- **Files:** engine/scanner.py

**Browser toolbar scrolls out of view**
- **Found:** Testing, 2026-03-21
- **Commit:** 0d8b501, 6e5a5a6, b2474c1, dbe35f1, 8c7d49b
- **Description:** Sticky positioning broken by negative margins, animation interactions.
- **Fix:** Changed to position:fixed with calculated top offset.
- **Files:** web/style.css, web/browser.js

**Dashboard stats sum all scans instead of latest**
- **Found:** Testing, 2026-03-22
- **Commit:** 384560d
- **Description:** Stats showed cumulative totals across all previous scans instead of current session only.
- **Fix:** Filter to most recent scan matching current staging directory.
- **Files:** web/dashboard.js

**Explorer and Recycle Bin open behind app window**
- **Found:** Testing, 2026-03-19
- **Commit:** bcd7461
- **Description:** Windows Explorer opened behind the pywebview window.
- **Fix:** Added `window.blur()` to push app to background when opening external windows.
- **Files:** web/browser.js, web/actions.js

**Hints always visible despite toggle**
- **Found:** Testing, 2026-03-23
- **Commit:** c804725
- **Description:** Dashboard hints stayed visible when disabled in settings.
- **Fix:** Respect `show_hints` setting on dashboard render.
- **Files:** web/dashboard.js

**Right-click and paste disabled on input fields**
- **Found:** Testing, 2026-03-23
- **Commit:** 41aa356, 37be50d
- **Description:** pywebview suppresses context menu and Ctrl+V/C/X/A at WebView2 level. Users couldn't paste folder paths.
- **Fix:** Added event listeners on input/textarea elements to enable native keyboard shortcuts and context menu.
- **Files:** web/app.js

**Review action bar scrolls horizontally instead of wrapping**
- **Found:** Testing, 2026-03-23
- **Commit:** (this session)
- **Description:** `overflow-x: auto` on action bar caused horizontal scroll. Buttons didn't wrap on narrow windows.
- **Fix:** Replaced `overflow-x: auto` with `flex-wrap: wrap`. Removed `flex-shrink: 0` from `.action-buttons`.
- **Files:** web/style.css

**Rescan button routes through wizard instead of scan-config**
- **Found:** Testing, 2026-03-22
- **Commit:** 4ed0a9f
- **Description:** Dashboard Rescan button went through wizard Step 2, triggering "Complete migration first" toast.
- **Fix:** Navigate directly to scan-config.
- **Files:** web/dashboard.js

**Verify copy uses wrong variable names**
- **Found:** Audit Phase 2, 2026-03-22
- **Commit:** a461d69
- **Description:** Error handling in `verify_copy()` referenced undefined variables, breaking move counter and copy verification.
- **Fix:** Corrected variable references.
- **Files:** engine/actions.py

**Console window flashes during operations**
- **Found:** Testing, 2026-03-23
- **Commit:** ecbfa94
- **Description:** robocopy and PowerShell subprocess console windows briefly visible.
- **Fix:** Hidden with `STARTUPINFO` flags (`SW_HIDE`).
- **Files:** engine/staging.py, engine/actions.py

---

## Bug Statistics

| Category | Count |
|----------|-------|
| Critical (crash/security) | 6 |
| High priority (functionality) | 14 |
| Security fixes | 8 |
| Medium priority (UX/data) | 11 |
| **Total resolved** | **39** |
| **Currently open** | **0** |

---

## Audit History

- **Audit #1 (2026-03-19):** 29 issues identified across safety, performance, algorithmic, and polish categories. All resolved in Phases 1-4.
- **Audit #2 (2026-03-20):** 5 critical bugs + 7 before-release items. All resolved same day.
- Audit reports archived in `Auditor/` directory.

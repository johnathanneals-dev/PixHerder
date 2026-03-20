# DupeFinder TODO

Persistent task list tracked in the repo. Updated with every commit cycle.

---

## In Progress

- [ ] "Choose another destination" option for Send Files Home
- [ ] Audit all navigation: ensure buttons everywhere except top menu text links
- [ ] Recycle Bin capacity indicator before bulk recycle operations
- [ ] "Delete All Remaining" button accessible from review process
- [ ] My Files browser: add "Move to Keepers" and "Move to Be Reviewed" buttons
- [ ] Move to Keepers: let user choose My Files, Removed Duplicates, or both as source

## Planned

- [ ] Multiple source folder support (import from several directories, manifest tracks per-file origin)
- [ ] Keepers folder workflow -- rescan Removed Duplicates, promote confirmed-good files to Verified Keepers
- [ ] Batch/chunked scanning for large collections (process in configurable chunks)
- [ ] Large collection optimization (BK-tree or VP-tree for perceptual comparison at 50k+ files)
- [ ] Code modularization -- split server.py into route modules, split index.html into separate CSS/JS
- [ ] Marketability -- branding, installer, landing page, packaging
- [ ] Thumb drive portable mode -- running from USB with virtual environment
- [ ] Additional keyboard shortcuts (E=execute, F=finish, Space=lightbox, 1-9=jump to group)
- [ ] Numbered menu items matching wizard step numbers (click number to jump to wizard step)
- [ ] File Safety / Expert mode toggle (reduces dialog count for experienced users)
- [ ] Server restart reliability -- os.execv() hangs, needs better restart mechanism
- [ ] Testing data tracking doc for consistency across test sessions
- [ ] Dashboard stats: show cumulative session totals instead of zeros when no active scan
- [ ] "Continue to Finalize" rename to "Access Wizard Steps" with updated explanation
- [ ] Wizard steps should stay accessible/clickable when conditions are met, not grey out when clicking another step
- [ ] Built-in #help view with anchored topics, replacing verbose UI explanations with "Learn more" links
- [ ] Help section navigation: full nav + "Back to where I was" button remembering previous view

## Completed

- [x] Top menu redesign: Dashboard | Migrate | Scan | Review | Finalize | Activity | Settings
- [x] Grey out nav items when not applicable
- [x] Rename Advanced Scan to Direct Scan
- [x] Rescan boxes on dashboard (Removed Duplicates + Verified Keepers, greyed out if empty)
- [x] Fix "Choose a different step" button missing border
- [x] Post-action navigation: horizontal stage buttons replacing redundant Back to Dashboard
- [x] Perceptual threshold explanation on scan config
- [x] Return to Dashboard button on scan config
- [x] Toast improvements: warning/error toasts blink and stay longer
- [x] Rename Keep All to Keep This Group for clarity
- [x] Fix staging folder discovery bug (os.listdir arbitrary order)
- [x] File safety documentation expanded (migration never touches originals)
- [x] Blocking progress view (#working) for all file operations
- [x] Fix inflated file counts in execute actions with Both scan mode
- [x] Fix wizard skipping to Stage 4 after Send Files Home (clear in-memory staging)
- [x] UX overhaul: button relabeling, keeper selection, no-dupes flow
- [x] Standardize dialog layout, button colors, button sizes
- [x] Plain English text throughout, exact folder names, no OneDrive references
- [x] Send Files Home full refund (all system folders)
- [x] Recycle Bin support (all deletes go to Recycle Bin)
- [x] Folder picker + quick-fill buttons on wizard Step 1
- [x] Click-to-toggle keep/dupe on images, multi-keep support
- [x] Browser compatibility warning banner
- [x] Design standards document (DESIGN_STANDARDS.md)
- [x] File security philosophy documented and enforced
- [x] Scan mode explanations below config in wizard Step 2
- [x] TODO.md persistent task tracker

## Won't Do / Deferred

- IE11/Edge Legacy support (document only, no polyfills)
- Windows 8.1 support (Windows 10 1803+ is minimum)

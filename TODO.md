# DupeFinder TODO

Persistent task list tracked in the repo. Updated with every commit cycle.

---

## In Progress

- [ ] Scan mode explanations below config in wizard Step 2 (what each mode does, threshold guidance)
- [ ] Dynamic stage navigation replacing "Finished with Scanning" (label changes based on state, stage picker dialog)
- [ ] "Choose another destination" option for Send Files Home
- [ ] Send Files Home progress indicator (currently no visual feedback during restore)

## Planned

- [ ] Multiple source folder support (import from several directories, manifest tracks per-file origin)
- [ ] Keepers folder workflow — rescan Removed Duplicates, promote confirmed-good files to Verified Keepers
- [ ] Batch/chunked scanning for large collections (process in configurable chunks)
- [ ] Large collection optimization (BK-tree or VP-tree for perceptual comparison at 50k+ files)
- [ ] Code modularization — split server.py into route modules, split index.html into separate CSS/JS
- [ ] Marketability — branding, installer, landing page, packaging
- [ ] Thumb drive portable mode — running from USB with virtual environment
- [ ] Additional keyboard shortcuts (E=execute, F=finish, Space=lightbox, 1-9=jump to group)
- [ ] Step 2 cancel button back to dashboard

## Completed

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

## Won't Do / Deferred

- IE11/Edge Legacy support (document only, no polyfills)
- Windows 8.1 support (Windows 10 1803+ is minimum)

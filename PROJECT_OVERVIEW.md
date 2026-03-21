# DupeFinder Project Overview

## What does DupeFinder do?

DupeFinder is a desktop application that finds and helps you clean up duplicate images. It scans a folder of photos, identifies duplicates using two methods (exact file matching via MD5 checksums, and visual similarity via perceptual hashing), then presents the results in a side-by-side review interface where you decide what to keep and what to remove.

The key differentiator is its safety-first approach: DupeFinder never permanently deletes anything. All removals go to the Windows Recycle Bin, giving you a final safety net. Files are always copied to a local workspace before scanning, so your originals are never touched during the process.

## Who is it for?

DupeFinder is being developed as a general-purpose tool for everyday Windows users, not just technical people. The target audience is anyone with a large photo collection that has accumulated duplicates over time -- particularly people using OneDrive-synced folders like Pictures, where duplicates tend to pile up from phone syncs, backups, and manual copies.

The UI is designed so that someone with no technical background can follow the guided wizard from start to finish without needing to understand what is happening behind the scenes. Button labels, dialog text, and explanations are all written in plain, non-technical language.

Currently in active development and testing by the developer, with plans for broader distribution once the core workflow is polished and stable.

## How do you launch it?

1. Run `setup.bat` once (downloads a portable Python runtime, installs dependencies, creates desktop shortcut)
2. Double-click the DupeFinder desktop shortcut (or `launch.vbs`)
3. A native application window opens with the DupeFinder interface

The application runs as a pywebview native window (using the system's Edge WebView2 engine). A lightweight internal HTTP server handles image display, but all user interaction flows through a direct Python-to-JavaScript bridge -- no browser tab, no URL to remember, no orphaned tabs.

## What is the typical workflow?

### Guided Wizard (recommended for most users)

1. **Migrate** -- Point DupeFinder at your photos folder (e.g., OneDrive Pictures). It copies the images to a local workspace called "My Files" so your originals stay safe and untouched during the entire process.

2. **Scan** -- Choose a scan mode:
   - *Exact (MD5)* -- Finds files that are byte-for-byte identical. Fast, zero false positives.
   - *Perceptual* -- Finds images that look visually similar even if they differ in size, compression, or format. Adjustable similarity threshold.
   - *Both* -- Runs exact first, then perceptual on the remaining files. Recommended for thorough cleaning.

3. **Review** -- DupeFinder presents duplicate groups one at a time. For each group, you see the images side by side and decide which to keep. You can:
   - Click an image to toggle it between "keep" and "duplicate"
   - Keep multiple files from a group if you want
   - Use "Mark All Remaining" to bulk-process when you are confident
   - Work through groups in manageable batches (50, 100, 250, 500, or all at once)
   - Close the app and come back later -- your decisions are auto-saved

4. **Finalize** -- When you are satisfied:
   - Files you marked as duplicates go to the Windows Recycle Bin (recoverable)
   - Files you kept are sent back to their original folder
   - DupeFinder cleans up its workspace

### Additional capabilities

- **Rescue and Review** -- If you change your mind, cycle files from Removed Duplicates back into My Files for another scan pass at a different threshold
- **Start Over** -- Consolidate all system folders back into My Files for a fresh scan
- **Send Files Home** -- A full refund: returns every file from every system folder back to the original location, cleans up silently
- **Direct Scan** -- Skip the wizard and scan any folder directly (for users comfortable with the tool)

### The three system folders

- **My Files** -- The working area where scanning and review happen
- **Removed Duplicates** -- Where files marked as duplicates are held until you finalize
- **Verified Keepers** -- A safe zone for files confirmed as good (used during iterative review)

## Has it been working well? What prompted the audit?

The core scanning and review workflow is functional and has been tested with real photo libraries of 20,000+ images. The audit was prompted by several factors:

1. **File safety concerns** -- During testing, the finish flow was found to permanently delete files from the OneDrive source folder via `os.remove()` fallbacks when PowerShell Recycle Bin calls failed. This was the most critical finding and has since been fixed -- all delete operations now exclusively use the Recycle Bin, and files are left in place if recycling fails.

2. **Security review** -- A directory traversal vulnerability was discovered in the image serving endpoint that could allow reading arbitrary files from the system. This has been patched with path validation.

3. **Architecture transition** -- The app was migrated from a browser-based interface (Python HTTP server + browser tab) to a native window (pywebview). This eliminated a class of UX issues (orphaned tabs, window focus problems, heartbeat auto-shutdown complexity, browser compatibility concerns) but introduced a new communication layer (Python-JS bridge) that needs verification.

4. **Memory and performance** -- The Pillow Image library was leaking file handles during large scans (not using context managers), and images were being loaded fully into memory for serving (problematic with large DSLR photos). Both have been fixed.

5. **Preparation for distribution** -- The tool is being prepared for use by non-technical users. The audit helps ensure the codebase is solid before broader testing and eventual release.

### What has been fixed so far

- All `os.remove()` fallbacks removed (files left in place on Recycle Bin failure)
- Directory traversal vulnerability patched (path validation + 403 response)
- Image streaming (shutil.copyfileobj instead of full file read into memory)
- Pillow Image leak fixed (context manager)
- Disk space check before migration
- Manifest validation on restore operations
- Decision file cleanup when scans are deleted
- Dedicated /api/staging/reset endpoint (replaced unsafe workaround)
- pywebview native window migration (eliminates browser-specific issues)

### Known remaining areas

- PowerShell recycling is per-file (slow for thousands of files) -- batch processing planned
- Default workspace location is in temp directory (Windows Storage Sense could clean it up)
- No automated tests or CI pipeline
- Some Phase 2 audit fixes still pending (see TODO.md)

# DupeFinder User's Manual

## Quick Start

1. Double-click the **DupeFinder** shortcut on your desktop (see setup below)
2. Your browser opens to `http://127.0.0.1:8787`
3. **Bookmark the page** (Ctrl+D) when prompted on the dashboard
4. Click **Start Guided Cleanup** and follow the 4-step wizard
5. Click **Shut Down** in the status bar when done

---

## First-Time Setup

1. Copy the DupeFinder folder to wherever you want it (your PC, a thumb drive, etc.)
2. Double-click **setup.bat** inside the folder
3. Setup will download Python, install dependencies, and generate launchers
4. When prompted, choose **Y** to create a desktop shortcut
5. That's it -- double-click the shortcut (or `launch.vbs`) to start

Setup only needs to run once. If you move the folder to a new location, run `setup.bat` again.

The server runs hidden in the background. The status bar at the bottom of the browser shows it's running. Use **Shut Down** to stop it cleanly, or **Restart** to apply setting changes or recover from errors. If you need to debug, use `launch.bat` instead (shows a terminal window with error output).

### Uninstalling

1. Shut down the server from the browser
2. Delete the DupeFinder folder
3. Delete the desktop shortcut if you created one
4. Optionally delete temp folders used for staging and dupes (found in your system temp directory)

### Bookmarking

The desktop shortcut opens a browser tab every time you launch DupeFinder. If you see multiple tabs after restarting your browser, close the extras. Bookmarking (Ctrl+D) is still handy for quick access without relaunching.

---

## Guided Cleanup Wizard

The recommended way to use DupeFinder. Click **Start Guided Cleanup** on the dashboard.

### Step 1: Migrate

OneDrive sync interferes with scanning (cloud-only files, file locks, sync prompts). This step copies your images to a local staging folder where DupeFinder can work without interruption. Your originals remain untouched.

- Use the quick-fill buttons (**OneDrive Pictures**, **Pictures**, **Desktop**) or click **Browse** to select your source folder
- Click **Begin Migration**
- Watch the progress bar as files are copied locally
- When complete, the step shows a checkmark and Step 2 opens

If you close the browser and come back later, the wizard detects your existing staging session and picks up where you left off.

### Step 2: Configure & Scan

Choose how to scan for duplicates:

- **Exact (MD5)** -- finds byte-for-byte identical files. Fast, zero false positives. Start here.
- **Perceptual** -- finds visually similar images even if resized or recompressed. Slower.
- **Both** -- runs both methods.
- **Perceptual threshold** (0-20): how similar images must be. Lower = stricter.
  - 0 = identical visual content
  - 5 = near-duplicate (default)
  - 10+ = catches more but may flag false positives
- **Include subfolders**: scan recursively (default: on)

Click **Start Scan** and watch progress. When complete, Step 3 opens.

**Best practice for multiple passes:**
1. First pass: Exact only -- knock out guaranteed duplicates
2. Second pass: Perceptual at threshold 2-3 -- catch resized/recompressed copies
3. Third pass: Perceptual at threshold 5-8 -- find more aggressive edits (review carefully)

Use the **Rescan** button in Step 4 to return here after each pass.

### Step 3: Review & Sort

Click **Open Review** to enter the full review interface.

Each duplicate group shows:
- The **KEEP** image (green badge) -- the one DupeFinder recommends keeping
- One or more **DUPE** images (red badge) -- candidates for removal
- File details: name, folder, size, distance score

**Actions per group:**
- **Skip** -- keep all files, do nothing
- **Move** -- mark dupes for moving to the dupes folder
- **Delete** -- mark dupes for permanent deletion

**Keyboard shortcuts:**
| Key | Action |
|-----|--------|
| Left/Right arrows | Previous/next group |
| S | Skip this group |
| M | Mark dupes for move |
| D | Mark dupes for delete |
| Escape | Close image zoom |

**Toolbar features:**
- Sort by: default, file size, reclaimable space, distance
- Filter: all, unreviewed, move, delete, skip
- Search by filename or folder
- Bulk actions: Mark All for Move, Skip All
- Click any image to zoom in -- use **Delete This File** to remove it, or **Back** to return to the group

**Action bar (bottom of screen):**
The action bar stays fixed at the bottom of your screen so you always have access to:
- Arrow buttons to navigate between groups
- Skip, Move, Delete for the current group
- All: Move and All: Skip for bulk decisions
- Execute to carry out your decisions

If no duplicate groups are found, you'll see buttons to go back to the dashboard or rescan with different settings.

When done reviewing, click **Execute** to carry out your decisions. After actions complete, click **Return to Wizard** to proceed to Step 4. If all files in a scan are successfully processed, the scan report is automatically removed from the Previous Scans list.

### Step 4: Explore & Finalize

Browse your files and decide next steps:

- **Cleaned Files** -- opens a file browser showing your staging folder (originals minus removed dupes). Navigate folders with breadcrumbs, view thumbnails, click to zoom.
- **Removed Duplicates** -- browse the dupes folder to verify nothing was wrongly removed.
- **Rescan** -- return to Step 2 for another pass (Step 1 stays complete)
- **Sync Back to OneDrive** -- apply your cleanup to the original OneDrive folder (deletes originals that were removed from staging)
- **Clean Up Staging** -- see "Finishing Up" below for safe cleanup options

When you're done with the wizard, return to the dashboard for the one-click finish option.

---

## File Browser

The built-in file browser shows image thumbnails in a grid. Features:
- Folder navigation with clickable breadcrumb trail
- Sort by name, size (largest first), or date (newest first)
- Infinite scroll -- loads more images as you scroll down
- Click any image to view full-size in the lightbox with a **Delete** button
- Delete empty folders by hovering and clicking the red X
- **Open in Explorer** -- opens the current folder in Windows File Explorer for bulk operations. DupeFinder minimizes automatically and refreshes when you switch back.
- **Scan for Duplicates** -- kicks off a scan on the folder you're browsing
- **Back** button stays visible as you scroll and returns to where you came from (dashboard or wizard)

The browser is restricted to the staging and dupes folders for security.

---

## Finishing Up

When you're done scanning and reviewing, the dashboard offers a one-click finish:

1. Click **Finished with Scanning** on the dashboard (or the **Finish** link in the top nav)
2. A summary page shows exactly what will happen:
   - How many files in Cleaned Files will be sent back to OneDrive
   - How many files in Removed Duplicates will be sent to the Recycle Bin
3. Review the OneDrive warning (see Important Notes below)
4. Click **Finish Now** and confirm
5. DupeFinder sends your files home, recycles duplicates, and cleans up the workspace

After finishing, duplicates are in your Windows Recycle Bin -- you can recover them from there if you change your mind.

### Advanced Options

Below the "Finished with Scanning" button, the dashboard also shows:

- **Send Files Home** -- return cleaned files to OneDrive without recycling dupes
- **Clean Up Workspace** -- offers a choice: send files home or send to Recycle Bin
- **Rescue & Review** -- cycle dupes back for another scan pass (see below)
- **Delete All Remaining** -- permanently delete everything in the dupes folder

---

## Rescue & Review

After running scans and moving duplicates, the Removed Duplicates folder may contain files you want to keep. The **Rescue & Review** button on the dashboard lets you cycle those files back through the scan and review process:

1. Click **Rescue & Review**
2. If your workspace (Cleaned Files) already has files, you'll be asked:
   - **Merge Dupes Into Workspace** -- adds the duplicates alongside your existing files so you can rescan everything together
   - **Sync Back to OneDrive First** -- sends your cleaned files back to OneDrive, then loads the duplicates
3. Scan the workspace to find duplicates among the recycled files
4. Review groups -- keep what matters, delete the rest
5. Repeat until you're confident nothing important remains
6. Use **Finished with Scanning** when satisfied

This is designed to be an iterative loop. Each pass reduces the file count as you separate keepers from junk.

### Verified Keepers

After rescanning duplicates and deleting the real dupes, click **Move to Keepers** to promote the remaining files to the Verified Keepers folder. These files are safe -- they won't be touched during further scanning, and they'll be sent home with your other files when you finish.

---

## Advanced Scan

For users who don't need the wizard, click **Advanced Scan** on the dashboard. This gives you direct access to the scan configuration without the staging step. Useful for scanning local folders that aren't managed by OneDrive.

If you scan a OneDrive folder directly, DupeFinder will detect it and offer to stage files first.

---

## Activity Log

Click the **Activity** tab to see a log of everything DupeFinder has done:
- Server starts and shutdowns (including auto-shutdowns)
- Scans started, completed, cancelled, or errored
- Staging operations
- File move/delete actions

Use **Clear** to reset the log.

---

## Auto-Shutdown

DupeFinder automatically shuts down if no browser tab is connected for 10 seconds. This prevents orphaned server processes. The server stays alive during long-running operations (scans, staging, actions) regardless of browser connection.

If the browser tab is accidentally closed, just reopen `http://127.0.0.1:8787` within 10 seconds. Or relaunch from the desktop shortcut.

---

## Resumable Scans

If a scan is interrupted (cancelled, crashed, or auto-shutdown), DupeFinder saves a checkpoint with all hashes computed so far. Next time you scan the same folder, it offers to resume from where it left off, skipping already-hashed files.

---

## Settings

Click the **Settings** tab to customize defaults:
- **Threshold**: default perceptual similarity threshold (0-20)
- **Move destination**: default folder for moving dupes (default: `C:\Temp\dupes`)
- **Keep strategy**: how to pick which file to keep in each group
  - Largest file (default) -- keeps the highest quality version
  - Oldest file -- keeps the original by date
  - Newest file -- keeps the most recent version
  - Shortest filename -- keeps the cleanest name
- **Extensions**: which file types to scan (comma-separated)
- **Scan batch size**: how often DupeFinder saves progress during scanning (default 2000). Lower values protect against crashes but scan slightly slower.
- **Port**: server port (default 8787, requires restart -- you will be prompted to restart when saving a port change)

---

## System Requirements

- **Windows 10** version 1803 (April 2018 Update) or later
- A modern browser: Chrome 80+, Firefox 80+, Safari 14+, or Edge 80+
- Internet Explorer and Edge Legacy are not supported
- ~50 MB disk space for the app, plus temp space for staging (roughly equal to your pictures folder size)

If your browser is too old, a red warning banner will appear at the top of the page.

---

## Important Notes

### OneDrive
The Guided Cleanup wizard handles OneDrive automatically by staging files locally. If you use Advanced Scan on a OneDrive folder directly:
- **Pause OneDrive sync** first (right-click tray icon > Pause syncing)
- Run your operations
- Resume sync afterward
- If OneDrive asks to "Keep" or "Delete" files, choose **Delete** (or they'll be restored)

### File Safety
- DupeFinder uses **copy + delete** (not move) to avoid file locking issues
- Each file operation is independent -- one failure won't stop the rest
- Failed files are logged and shown in the UI
- Move operations are reversible: files go to your dupes folder
- The **Finish** flow and **Clean Up Workspace** send files to the Windows Recycle Bin -- you can recover them if needed
- The **Delete All Remaining** button permanently deletes files (not sent to Recycle Bin)

### Controlled Folder Access
Windows Defender's Controlled Folder Access is enabled. If the app can't create files, whitelist Python:
- Open **Windows Security** > **Virus & threat protection** > **Ransomware protection**
- Click **Allow an app through Controlled folder access**
- Add `C:\Program Files\Python313\python.exe`

---

## Troubleshooting

| Problem | Solution |
|---------|----------|
| **Launching** | |
| Double-clicking the shortcut does nothing | Make sure Python is installed at `C:\Program Files\Python313\python.exe`. Try `launch.bat` instead to see error messages in a terminal window |
| Browser doesn't open | The desktop shortcut should always open the browser. If not, navigate to `http://127.0.0.1:8787` manually |
| Page is blank or says "Unable to connect" | The server may still be starting up. Wait a few seconds and refresh. If it persists, try `launch.bat` to check for errors |
| "Address already in use" | Another instance is already running. Check your browser for an existing DupeFinder tab, or restart your computer to clear it |
| Multiple tabs appear | Your browser restored old tabs from a previous session. Close the extras and bookmark the page (Ctrl+D) |
| **Scanning** | |
| Scan seems stuck at a percentage | The progress bar tracks multiple phases. During "Comparing images..." the bar may move slowly on large collections -- this is normal. You can cancel and try an exact-only scan first |
| "Not enough images to compare" | The selected folder has fewer than 2 image files. Check the path and make sure "Include subfolders" is checked if your images are in subdirectories |
| Scan finds too many false positives | Lower the perceptual threshold. Start with exact-only scans, then try perceptual at threshold 2-3. Higher thresholds (10+) will match images that only look vaguely similar |
| Scan finds no duplicates | Your folder may not have duplicates at the current threshold. Try a higher threshold for perceptual scans, or check that you scanned the right folder |
| **Actions** | |
| "Access denied" on file operations | This is usually Windows Defender's Controlled Folder Access blocking Python. See the Controlled Folder Access section above to whitelist Python |
| "Skipped: X (already processed)" | Those files were already moved or deleted in a previous run. This is normal when re-running actions on the same scan |
| My scan disappeared from the list | Scan reports are automatically removed after all their files have been successfully processed. This is expected -- the scan's work is done |
| Images don't load in the review screen | The image files may have been moved or deleted since the scan. Rescan to get a fresh report |
| **File Browser** | |
| Error when clicking a folder | The folder may not exist or may be outside the allowed directories (staging and dupes folders only). Use the breadcrumb trail to navigate back |
| Folder shows "This folder is empty" | The folder contains no image files. It may have subfolders (not shown) or non-image files |
| **Server** | |
| Server shuts down unexpectedly | DupeFinder auto-shuts down 10 seconds after you close the browser tab. Relaunch from the desktop shortcut |
| Server seems unresponsive | Click **Restart** in the status bar at the bottom of the page. If the page is completely unresponsive, close the tab and relaunch from the shortcut |
| Changed a setting but nothing happened | Most settings apply immediately. The server port requires a restart -- you will be prompted to restart when saving a port change |
| **OneDrive** | |
| Migration/staging is slow | Copying thousands of images takes time, especially from OneDrive. The first migration is the slowest; subsequent ones can reuse the existing staging folder |
| OneDrive asks to "Keep" or "Delete" after sync-back | Choose **Delete**. If you choose "Keep", OneDrive will restore the files you just removed |
| "File not found" errors during move | Files may be OneDrive cloud-only (not downloaded locally). Use the Guided Cleanup wizard to stage files locally first |
| **Finishing** | |
| Recycle Bin operation failed | DupeFinder falls back to permanent delete if PowerShell is unavailable. Check that PowerShell is installed and not blocked by group policy |
| Where did my recycled files go? | They are in the Windows Recycle Bin (on your desktop). Right-click it to restore files if needed |

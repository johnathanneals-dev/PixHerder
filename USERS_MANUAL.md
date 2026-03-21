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

---

## Guided Cleanup Wizard

The recommended way to use DupeFinder. Click **Start Guided Cleanup** on the dashboard.

### Step 1: Migrate

DupeFinder makes a working copy of your pictures so it can scan without interruption. Your originals stay exactly where they are -- nothing is changed or deleted.

- Use the quick-fill buttons (**OneDrive Pictures**, **Pictures**, **Desktop**) or click **Browse** to select your source folder
- Click **Begin Migration** (or **Cancel** to return to the dashboard)
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

Each duplicate group shows all the matching files side by side. DupeFinder picks one to keep (green KEEP badge) and marks the rest as duplicates (red DUPE badge).

**Choosing which files to keep:**
Click any image to toggle it between KEEP (green) and DUPE (red). You can mark multiple files as KEEP in the same group -- at least one must always be kept. Click the **Zoom** button on any image to see it full-size.

**Actions per group:**
- **Keep All** -- keep every file in this group, don't remove anything
- **Mark as Duplicate** -- mark the DUPE files for removal to Removed Duplicates
- **Delete** -- mark the DUPE files for permanent deletion

**Keyboard shortcuts:**
| Key | Action |
|-----|--------|
| Left/Right arrows | Previous/next group |
| S | Keep All (keep every file) |
| M | Mark as Duplicate |
| D | Delete |
| Escape | Close image zoom |

**Toolbar features:**
- Sort by: default, file size, reclaimable space, distance
- Filter: all, unreviewed, marked as duplicate, marked for delete, keeping
- Search by filename or folder
- **Mark All Remaining** -- marks all unreviewed groups as duplicates (preserves your previous decisions)
- **Keep All Remaining** -- keeps all unreviewed groups

**Action bar (bottom of screen):**
The action bar stays fixed at the bottom so you always have access to navigation, actions, and **Exit** to return to the dashboard.

If no duplicate groups are found, you'll see buttons to rescan with different settings or return to the dashboard.

When done reviewing, click **Apply Decisions** to carry out your choices. After actions complete, click **Return to Wizard** to proceed to Step 4.

### Step 4: Explore & Finalize

Browse your files and decide next steps:

- **My Files** -- browse the files you're keeping
- **Removed Duplicates** -- check that nothing was wrongly removed
- **Rescan** -- return to Step 2 for another pass with different settings
- **Finished with Scanning** -- wraps everything up (see "Finishing Up" below)
- **Back to Dashboard** -- return to the dashboard for more options

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

The browser is restricted to the My Files, Removed Duplicates, and Verified Keepers folders for security.

---

## Finishing Up

When you're done scanning and reviewing, the dashboard offers a one-click finish:

1. Click **Finished with Scanning** on the dashboard (or the **Finish** link in the top nav)
2. A summary page shows exactly what will happen:
   - How many files in My Files will be kept safe
   - How many files in Removed Duplicates will be sent to the Recycle Bin
3. Click **Finish Now** and confirm
4. DupeFinder keeps your files safe, recycles duplicates, and cleans up

After finishing, duplicates are in your Windows Recycle Bin -- you can recover them from there if you change your mind.

### More Options

Below the "Finished with Scanning" button, the dashboard also shows:

- **Send Files Home** -- put all your files back where they came from. Nothing gets deleted.
- **Remove Workspace** -- choose to send files home or to the Recycle Bin, then remove the local copy
- **Start Over** -- put all files back into My Files so you can rescan everything from scratch
- **Rescue & Review** -- move Removed Duplicates back to My Files for another scan pass (see below)
- **Move to Keepers** -- save Removed Duplicates files as confirmed keepers (see below)
- **Delete All Remaining** -- send everything in Removed Duplicates to the Recycle Bin

When you use any of these options, DupeFinder takes you to a progress screen while it works. You can't accidentally click other buttons during the operation. When it's done, you'll see a summary and a **Continue** button to return to the dashboard.

---

## Rescue & Review

After running scans and moving duplicates, the Removed Duplicates folder may contain files you want to keep. The **Rescue & Review** button on the dashboard lets you cycle those files back for another look:

1. Click **Rescue & Review**
2. If My Files already has files, you'll be asked:
   - **Merge Dupes** -- files from Removed Duplicates will be merged with the files in My Files
   - **Return / Reload** -- sends your My Files home first, then brings the Removed Duplicates back for review
3. Scan again to find the real duplicates
4. Review groups -- click images to toggle keep/dupe, then apply your decisions
5. Repeat until you're confident nothing important remains
6. Use **Finished with Scanning** when satisfied

This is designed to be an iterative loop. Each pass reduces the file count as you separate keepers from junk.

### Verified Keepers

After rescanning and deleting the real duplicates, click **Move to Keepers** to save the remaining Removed Duplicates files as confirmed keepers. Files in Verified Keepers are safe -- they won't be touched during further scanning, and they'll be sent home with your other files when you finish.

---

## Scanning Multiple Folders

DupeFinder currently scans one folder at a time. To find duplicates across multiple folders (e.g., Pictures and Desktop), run them as separate passes:

1. **First folder:** Start the wizard, migrate your first folder, scan, review, and finish
2. **Send files home** when you're satisfied with the first folder's results
3. **Start again:** Click Start Guided Cleanup, pick your second folder, and repeat

Each pass is independent -- your originals are never changed until you explicitly send files home or finish.

**Tip:** If you want to find duplicates *between* two folders (not just within each one), copy both folders into a single parent folder first, then scan that parent folder with "Include subfolders" checked.

---

## Advanced Scan

For users who don't need the wizard, click **Advanced Scan** on the dashboard. This gives you direct access to the scan configuration without the migration step. Useful for scanning folders that don't need a working copy made first.

If you scan a synced folder (like OneDrive), DupeFinder will detect it and offer to make a local copy first.

---

## Activity Log

Click the **Activity** tab to see a log of everything DupeFinder has done:
- Server starts and shutdowns
- Scans started, completed, cancelled, or errored
- Staging operations
- File move/delete actions

Use **Clear** to reset the log.

---

## Resumable Scans

If a scan is interrupted (cancelled or crashed), DupeFinder saves a checkpoint with all hashes computed so far. Next time you scan the same folder, it offers to resume from where it left off, skipping already-hashed files.

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

### Synced Folders (OneDrive, etc.)
The Guided Cleanup wizard handles synced folders automatically by making a working copy. If you use Advanced Scan on a synced folder directly:
- **Pause sync** first (right-click tray icon > Pause syncing)
- Run your operations
- Resume sync afterward
- If your system asks to "Keep" or "Delete" files, choose **Delete** (or they'll be restored)

### File Safety

DupeFinder is designed with file security as the top priority. **No user file is ever permanently deleted by DupeFinder.** All delete operations send files to the Windows Recycle Bin, where you can recover them if needed.

- **Your originals are never touched during migration.** DupeFinder copies files to a local workspace -- it never moves or deletes your originals. If the process crashes or is interrupted, your originals are exactly where they were. The partial copy can be discarded and restarted.
- **Only you can trigger actions that affect originals.** "Send Files Home" and "Finish" are the only operations that copy files back to your original folder. Nothing happens to your originals until you explicitly choose one of these options.
- DupeFinder uses **copy + delete** (not move) to avoid file locking issues
- Each file operation is independent -- one failure won't stop the rest
- Failed files are logged and shown in the UI
- Move operations are reversible: files go to Removed Duplicates
- All delete operations (individual files, folders, Delete All Remaining, review deletions) go to the **Recycle Bin**
- The **Finish** flow sends Removed Duplicates to the Recycle Bin
- **Send Files Home** puts everything back where it came from -- nothing is deleted
- The **Finish** flow never deletes your originals. It copies kept files back and recycles local duplicate copies only.

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
| Window doesn't open | Check Task Manager for lingering python.exe processes and end them, then relaunch |
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
| **Application** | |
| DupeFinder closes unexpectedly | Relaunch from the desktop shortcut. Check Task Manager for orphaned python.exe processes |
| Changed a setting but nothing happened | Most settings apply immediately. The server port requires closing and reopening DupeFinder |
| **Synced Folders** | |
| Migration is slow | Copying thousands of images takes time. The first migration is the slowest; subsequent ones can reuse the existing copy |
| System asks to "Keep" or "Delete" after finishing | Choose **Delete**. If you choose "Keep", the sync service will restore the files you just removed |
| "File not found" errors during move | Some files may be cloud-only (not downloaded locally). Use the Guided Cleanup wizard to make a local copy first |
| **Finishing** | |
| Recycle Bin operation failed | DupeFinder falls back to permanent delete if PowerShell is unavailable. Check that PowerShell is installed and not blocked by group policy |
| Where did my recycled files go? | They are in the Windows Recycle Bin (on your desktop). Right-click it to restore files if needed |

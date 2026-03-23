# PixHerder User's Manual

## Quick Start

1. Double-click the **PixHerder** shortcut on your desktop (see setup below)
2. The PixHerder window opens
3. Click **Start Guided Cleanup** and follow the 4-step wizard
4. Close the window when done

---

## First-Time Setup

1. Copy the PixHerder folder to wherever you want it (your PC, a thumb drive, etc.)
2. Double-click **setup.bat** inside the folder
3. Setup will download Python, install dependencies, run security checks, and generate launchers
4. When prompted, choose **Y** to create a desktop shortcut
5. That's it -- double-click the shortcut (or `launch.vbs`) to start

Setup only needs to run once. If you move the folder to a new location, run `setup.bat` again.

PixHerder opens as a native desktop window. The status bar at the bottom shows the server is running. Close the window to exit. If you need to troubleshoot, use `launch.bat` instead (shows a terminal window with error output).

### Uninstalling

1. Close the PixHerder window
2. Delete the PixHerder folder
3. Delete the desktop shortcut if you created one
4. Optionally delete temp folders used for staging and dupes (found in your system temp directory)

---

## Windows Security Setup

PixHerder works with your existing Windows security settings, but some features may need permission. The setup script checks for these automatically and will tell you if anything needs attention.

### Controlled Folder Access (CFA)

If Windows Defender's Controlled Folder Access is turned on, you may need to allow PixHerder's Python to write files. Without this, scans may fail to save results.

**How to check and fix:**

1. Open **Windows Security** (search "Windows Security" in the Start menu)
2. Click **Virus & threat protection**
3. Scroll down to **Ransomware protection** and click **Manage ransomware protection**
4. If **Controlled folder access** is turned on, click **Allow an app through Controlled folder access**
5. Click **Add an allowed app** and browse to add these files from the PixHerder folder:
   - `python\pythonw.exe` (the main executable)
   - `python\python.exe` (used for troubleshooting)

If CFA is turned off, you don't need to do anything.

### PowerShell

PixHerder uses PowerShell to send files to the Windows Recycle Bin. This works on all standard Windows 10/11 installations. If your computer has restrictions on PowerShell (common in some work environments), file recycling may not work. In that case, files will stay where they are -- nothing is ever permanently deleted without your explicit action.

### Firewall

PixHerder uses a local connection (port 8787) to display images in the app window. This connection never leaves your computer -- no internet access is needed after setup. If a firewall (like Portmaster or a corporate firewall) blocks local connections, you may need to allow port 8787 for `127.0.0.1` only.

### Antivirus Software

Some antivirus programs (Norton, McAfee, Avast, etc.) may flag PixHerder because it uses Python scripts. This is a false positive. If your antivirus blocks PixHerder, add the PixHerder folder to your antivirus exclusion list.

---

## Guided Cleanup Wizard

The recommended way to use PixHerder. Click **Start Guided Cleanup** on the dashboard.

### Step 1: Migrate

PixHerder makes a working copy of your pictures so it can scan without interruption. Your originals stay exactly where they are -- nothing is changed or deleted.

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
- **Auto-recycle exact duplicates**: when checked, byte-for-byte identical files are automatically sent to the Recycle Bin without going through review. Keeps the largest file in each group. This is completely safe -- exact matches have zero false positives. Leave unchecked if you want to review everything yourself. Default: unchecked.
- **Scan batch size**: how many files to scan at once (All, 500, 1000, 2000, 5000). Default: 2000. After you review and act on one batch, the next scan picks up where it left off. Recommended for large collections.

Click **Start Scan** and watch progress. When complete, Step 3 opens.

**Recommended progressive approach for large collections:**

1. Set scan batch size to 2000 (default)
2. First pass: Exact only with auto-recycle on -- clears out guaranteed duplicates automatically
3. Review any remaining groups, apply decisions
4. Second pass: Perceptual at threshold 2-3 -- catch resized/recompressed copies
5. Third pass: Perceptual at threshold 5-8 -- find more aggressive edits (review carefully)
6. Each scan picks up where the last left off, so you work through the collection in manageable chunks

Use the **Rescan** button in Step 4 to return here after each pass.

### Step 3: Review & Sort

Click **Open Review** to enter the full review interface.

Each duplicate group shows all the matching files side by side. PixHerder picks one to keep (green KEEP badge) and marks the rest as duplicates (red DUPE badge).

**Image details shown on each card:**

- Image dimensions (e.g., 4032 x 3024)
- File size (e.g., 3.2 MB)
- Date modified (e.g., 2024-11-15)
- Similarity percentage (e.g., 98% similar) or "100% match" for exact duplicates

This information helps you decide which copy is the best quality. Click **Zoom** on any image to see it full-size -- the lightbox also shows these details at the bottom of the screen.

**Choosing which files to keep:**
Click any image to toggle it between KEEP (green) and DUPE (red). You can mark multiple files as KEEP in the same group -- at least one must always be kept. Click the **Zoom** button on any image to see it full-size.

**Actions per group:**
- **Keep All** -- keep every file in this group, don't remove anything
- **Mark as Duplicate** -- mark the DUPE files for removal to Recovery
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

- **Staging** -- browse the files you're keeping
- **Recovery** -- check that nothing was wrongly removed
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
- **Open in Explorer** -- opens the current folder in Windows File Explorer for bulk operations. PixHerder minimizes automatically and refreshes when you switch back.
- **Scan for Duplicates** -- kicks off a scan on the folder you're browsing
- **Back** button stays visible as you scroll and returns to where you came from (dashboard or wizard)

The browser is restricted to the Staging, Recovery, and Keepers folders for security.

---

## Finishing Up

When you're done scanning and reviewing, the dashboard offers a one-click finish:

1. Click **Finished with Scanning** on the dashboard (or the **Finish** link in the top nav)
2. A summary page shows exactly what will happen:
   - How many files in Staging will be kept safe
   - How many files in Recovery will be sent to the Recycle Bin
3. Click **Finish Now** and confirm
4. PixHerder keeps your files safe, recycles duplicates, and cleans up

After finishing, duplicates are in your Windows Recycle Bin -- you can recover them from there if you change your mind.

### More Options

Below the "Finished with Scanning" button, the dashboard also shows:

- **Send Files Home** -- put all your files back where they came from. Nothing gets deleted.
- **Remove Workspace** -- choose to send files home or to the Recycle Bin, then remove the local copy
- **Start Over** -- put all files back into Staging so you can rescan everything from scratch
- **Rescue & Review** -- move Recovery back to Staging for another scan pass (see below)
- **Move to Keepers** -- save Recovery files as confirmed keepers (see below)
- **Delete All Remaining** -- send everything in Recovery to the Recycle Bin

When you use any of these options, PixHerder takes you to a progress screen while it works. You can't accidentally click other buttons during the operation. When it's done, you'll see a summary and a **Continue** button to return to the dashboard.

---

## Rescue & Review

After running scans and moving duplicates, the Recovery folder may contain files you want to keep. The **Rescue & Review** button on the dashboard lets you cycle those files back for another look:

1. Click **Rescue & Review**
2. If Staging already has files, you'll be asked:
   - **Merge Dupes** -- files from Recovery will be merged with the files in Staging
   - **Return / Reload** -- sends your Staging home first, then brings the Recovery back for review
3. Scan again to find the real duplicates
4. Review groups -- click images to toggle keep/dupe, then apply your decisions
5. Repeat until you're confident nothing important remains
6. Use **Finished with Scanning** when satisfied

This is designed to be an iterative loop. Each pass reduces the file count as you separate keepers from junk.

### Keepers

After rescanning and deleting the real duplicates, click **Move to Keepers** to save the remaining Recovery files as confirmed keepers. Files in Keepers are safe -- they won't be touched during further scanning, and they'll be sent home with your other files when you finish.

---

## Auto-Recycle Exact Duplicates

When scanning with Exact (MD5) mode, you can check the **Auto-recycle exact duplicates** box on the scan config page. This tells PixHerder to skip the review step for byte-for-byte identical files and send them straight to the Recycle Bin.

**When to use it:**

- You have a large collection and want to clear out obvious duplicates quickly
- You trust that identical files (same size, same content, same checksum) are safe to remove
- You want to focus your review time on the trickier perceptual matches

**How it works:**

- Only affects exact (MD5) matches -- files that are bit-for-bit identical
- Keeps the largest file in each group (highest quality version)
- Duplicates go to the Windows Recycle Bin, so you can always recover them
- Zero false positives -- if two files have the same MD5 hash, they are the same file
- Does not affect perceptual matches, which still go through normal review

**When not to use it:**

- You want to manually review every group, even exact matches
- You want to choose which copy to keep based on filename or location rather than size

The checkbox is off by default. You can turn it on and off between scan passes.

---

## Recovery Archive

PixHerder keeps a safety net for recently recycled files. Before files are sent to the Recycle Bin, copies are saved in a recovery folder (PixHerder_Recovery).

**How it works:**

- The recovery archive keeps the 2 most recent operations (rolling 2-slot system)
- Each time you recycle files, the oldest slot is replaced with the new backup
- You can browse and restore files from the dashboard
- The archive is cleared automatically when you finish your session

**When to use it:**

- You recycled a batch and realized you wanted to keep some of those files
- You want a quick way to undo a recent action without digging through the Recycle Bin
- The Recycle Bin has too many files to search through easily

**Restoring files:**

1. Go to the dashboard
2. If the recovery archive has files, you'll see a restore option
3. Browse the available recovery slots
4. Select the files you want to restore

The recovery archive is a convenience feature on top of the Recycle Bin. Even after the archive is cleared, recycled files are still in the Windows Recycle Bin until you empty it.

---

## Chunked Scanning

For large photo collections, scanning everything at once can be overwhelming. Chunked scanning lets you work through your files in manageable batches.

**How it works:**

- On the scan config page, choose a scan batch size: All, 500, 1000, 2000, or 5000
- Default is 2000 files per batch
- PixHerder scans the first batch, then you review and act on those results
- The next scan automatically picks up where the last one left off
- Repeat until all files have been processed

**Recommended batch sizes:**

- **500** -- small batches, good for careful review of tricky collections
- **1000** -- moderate batches, balances speed and review quality
- **2000** (default) -- good for most collections, enough to find patterns without being overwhelming
- **5000** -- large batches for quick passes, best with auto-recycle on exact matches
- **All** -- scan everything at once, best for small collections (under 5000 files)

**Tips:**

- Start with the default (2000) and adjust based on how the review feels
- Combine with auto-recycle on exact matches to clear obvious duplicates first
- Each batch builds on the previous -- you never re-scan files you've already handled
- You can change the batch size between passes

---

## Scanning Multiple Folders

PixHerder currently scans one folder at a time. To find duplicates across multiple folders (e.g., Pictures and Desktop), run them as separate passes:

1. **First folder:** Start the wizard, migrate your first folder, scan, review, and finish
2. **Send files home** when you're satisfied with the first folder's results
3. **Start again:** Click Start Guided Cleanup, pick your second folder, and repeat

Each pass is independent -- your originals are never changed until you explicitly send files home or finish.

**Tip:** If you want to find duplicates *between* two folders (not just within each one), copy both folders into a single parent folder first, then scan that parent folder with "Include subfolders" checked.

---

## Advanced Scan

For users who don't need the wizard, click **Advanced Scan** on the dashboard. This gives you direct access to the scan configuration without the migration step. Useful for scanning folders that don't need a working copy made first.

If you scan a synced folder (like OneDrive), PixHerder will detect it and offer to make a local copy first.

---

## Activity Log

Click the **Activity** tab to see a log of everything PixHerder has done:
- Server starts and shutdowns
- Scans started, completed, cancelled, or errored
- Staging operations
- File move/delete actions

Use **Clear** to reset the log.

---

## Resumable Scans

If a scan is interrupted (cancelled or crashed), PixHerder saves a checkpoint with all hashes computed so far. Next time you scan the same folder, it offers to resume from where it left off, skipping already-hashed files.

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
- **Scan batch size**: how often PixHerder saves progress during scanning (default 2000). Lower values protect against crashes but scan slightly slower.
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

PixHerder is designed with file security as the top priority. **No user file is ever permanently deleted by PixHerder.** All delete operations send files to the Windows Recycle Bin, where you can recover them if needed.

- **Your originals are never touched during migration.** PixHerder copies files to a local workspace -- it never moves or deletes your originals. If the process crashes or is interrupted, your originals are exactly where they were. The partial copy can be discarded and restarted.
- **Only you can trigger actions that affect originals.** "Send Files Home" and "Finish" are the only operations that copy files back to your original folder. Nothing happens to your originals until you explicitly choose one of these options.
- PixHerder uses **copy + delete** (not move) to avoid file locking issues
- Each file operation is independent -- one failure won't stop the rest
- Failed files are logged and shown in the UI
- Move operations are reversible: files go to Recovery
- All delete operations (individual files, folders, Delete All Remaining, review deletions) go to the **Recycle Bin**
- The **Finish** flow sends Recovery to the Recycle Bin
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
| "Address already in use" | Another instance is already running. Check your browser for an existing PixHerder tab, or restart your computer to clear it |
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
| PixHerder closes unexpectedly | Relaunch from the desktop shortcut. Check Task Manager for orphaned python.exe processes |
| Changed a setting but nothing happened | Most settings apply immediately. The server port requires closing and reopening PixHerder |
| **Synced Folders** | |
| Migration is slow | Copying thousands of images takes time. The first migration is the slowest; subsequent ones can reuse the existing copy |
| System asks to "Keep" or "Delete" after finishing | Choose **Delete**. If you choose "Keep", the sync service will restore the files you just removed |
| "File not found" errors during move | Some files may be cloud-only (not downloaded locally). Use the Guided Cleanup wizard to make a local copy first |
| **Finishing** | |
| Recycle Bin operation failed | PixHerder falls back to permanent delete if PowerShell is unavailable. Check that PowerShell is installed and not blocked by group policy |
| Where did my recycled files go? | They are in the Windows Recycle Bin (on your desktop). Right-click it to restore files if needed |

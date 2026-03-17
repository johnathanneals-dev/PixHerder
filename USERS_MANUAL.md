# DupeFinder User's Manual

## Quick Start

1. Double-click the **DupeFinder** shortcut on your desktop (see setup below)
2. Your browser opens to `http://127.0.0.1:8787`
3. Click **Start Guided Cleanup** and follow the 4-step wizard
4. Click **Shut Down** in the status bar when done

---

## Desktop Shortcut Setup

1. Right-click your Desktop and choose **New > Shortcut**
2. In the location field, paste:
   ```
   C:\Projects\Duped\launch.vbs
   ```
3. Click **Next**, name it **DupeFinder**, click **Finish**
4. (Optional) Right-click the shortcut > **Properties** and set a custom icon

The server runs hidden in the background. The status bar at the bottom of the browser shows it's running. Use the **Shut Down** button to stop it cleanly. If you need to debug, use `launch.bat` instead (shows a terminal window with error output).

---

## Guided Cleanup Wizard

The recommended way to use DupeFinder. Click **Start Guided Cleanup** on the dashboard.

### Step 1: Migrate

OneDrive sync interferes with scanning (cloud-only files, file locks, sync prompts). This step copies your images to a local staging folder where DupeFinder can work without interruption. Your originals remain untouched.

- Enter your OneDrive Pictures path (e.g. `C:\Users\repom\OneDrive\Pictures`)
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
- Click any image to zoom in (lightbox)

When done reviewing, click **Execute Actions** to carry out your decisions. After actions complete, click **Return to Wizard** to proceed to Step 4.

### Step 4: Explore & Finalize

Browse your files and decide next steps:

- **Cleaned Files** -- opens a file browser showing your staging folder (originals minus removed dupes). Navigate folders with breadcrumbs, view thumbnails, click to zoom.
- **Removed Duplicates** -- browse the dupes folder to verify nothing was wrongly removed.
- **Rescan** -- return to Step 2 for another pass (Step 1 stays complete)
- **Sync Back to OneDrive** -- apply your cleanup to the original OneDrive folder (deletes originals that were removed from staging)
- **Clean Up Staging** -- delete the local staging copy when you're done

---

## File Browser

The built-in file browser shows image thumbnails in a grid. Features:
- Folder navigation with clickable breadcrumb trail
- Sort by name, size (largest first), or date (newest first)
- Infinite scroll -- loads more images as you scroll down
- Click any image to view full-size in the lightbox
- **Return** button goes back to the wizard

The browser is restricted to the staging and dupes folders for security.

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

DupeFinder automatically shuts down if no browser tab is connected for 30 seconds. This prevents orphaned server processes. The server stays alive during long-running operations (scans, staging, actions) regardless of browser connection.

If the browser tab is accidentally closed, just reopen `http://127.0.0.1:8787` within 30 seconds. Or relaunch from the desktop shortcut.

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
- **Port**: server port (default 8787, requires restart)

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
- **Delete operations are permanent** -- files are not sent to the recycle bin

### Controlled Folder Access
Windows Defender's Controlled Folder Access is enabled. If the app can't create files, whitelist Python:
- Open **Windows Security** > **Virus & threat protection** > **Ransomware protection**
- Click **Allow an app through Controlled folder access**
- Add `C:\Program Files\Python313\python.exe`

---

## Troubleshooting

| Problem | Solution |
|---------|----------|
| Browser doesn't open | Navigate manually to `http://127.0.0.1:8787` |
| "Address already in use" | Another instance is running. Close it or change the port in Settings |
| Images don't load | Check that the image files still exist at their original paths |
| "Access denied" on file operations | Pause OneDrive sync, check Controlled Folder Access |
| Scan seems stuck | Check the progress bar -- perceptual scans on large folders take time. Cancel and try exact-only |
| Server won't start | Make sure Python 3.13 is being used, not 3.14 |
| "File not found" errors during move | Files may be OneDrive cloud-only. Use the Guided Cleanup wizard to stage files locally first |
| Server shuts down unexpectedly | Auto-shutdown triggered (no browser tab for 30s). Relaunch from shortcut |
| Wizard shows wrong step | The wizard auto-detects your progress. If it's wrong, start fresh from Step 1 |

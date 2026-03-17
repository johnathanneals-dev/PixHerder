# DupeFinder User's Manual

## Quick Start

1. Double-click the **DupeFinder** shortcut on your desktop (see setup below), or run:
   ```
   python C:\Projects\Duped\dupefinder_app.py
   ```
2. Your browser opens to `http://127.0.0.1:8787`
3. Click **Start New Scan**, paste a folder path, and go.
4. Press `Ctrl+C` in the terminal window to shut down the server when you're done.

---

## Desktop Shortcut Setup

1. Right-click your Desktop and choose **New > Shortcut**
2. In the location field, paste:
   ```
   "C:\Program Files\Python313\python.exe" "C:\Projects\Duped\dupefinder_app.py"
   ```
3. Click **Next**, name it **DupeFinder**, click **Finish**
4. (Optional) Right-click the shortcut > **Properties**:
   - Set **Start in** to `C:\Projects\Duped`
   - Click **Change Icon** and pick one you like
   - Click **OK**

When you double-click the shortcut, a terminal window appears (this is the server) and your browser opens automatically.

---

## Walkthrough

### Dashboard

The home screen. Shows:
- Quick stats from your most recent scan (groups found, duplicates, reclaimable space)
- A list of previous scan results you can review or delete
- The **Start New Scan** button

### Scan Configuration

- **Folder path**: Paste the full path to the folder you want to scan (e.g. `C:\Users\repom\OneDrive\Pictures`)
- **Scan mode**:
  - **Exact** -- finds byte-for-byte identical files (fast, uses MD5 hash)
  - **Perceptual** -- finds visually similar images even if resized or recompressed (slower, uses pHash)
  - **Both** -- runs both methods (recommended)
- **Perceptual threshold**: How similar images must be to count as duplicates. Lower = stricter.
  - 0 = identical perceptual hash
  - 5 = near-duplicate (default, good for most cases)
  - 10 = similar (catches more, but may flag false positives)
  - 15+ = loose (not recommended)
- **Recursive**: When checked, scans subfolders too (default: on)

Click **Start Scan** to begin.

### Scan Progress

Shows real-time progress as the scan runs:
- Current stage (discovering files, MD5 hashing, pHash hashing, comparing)
- Files processed out of total
- Elapsed time and estimated time remaining
- Error count (files that couldn't be read)

You can **Cancel** at any time. When the scan finishes, click **Review Results**.

**Timing note**: For ~22,000 images, expect roughly:
- Exact-only scan: a few minutes
- Perceptual scan: longer, depending on your hardware
- The progress bar and ETA keep you informed

### Review

This is where you decide what to keep and what to remove. Each duplicate group shows:
- The **KEEP** image (green badge) -- the one DupeFinder recommends keeping
- One or more **DUPE** images (red badge) -- candidates for removal
- File details: name, folder, size, date modified
- Distance score (for perceptual matches) -- lower = more similar

**Actions per group:**
- **Skip** -- keep all files in this group, do nothing
- **Move** -- mark the dupes for moving to a separate folder
- **Delete** -- mark the dupes for permanent deletion

**Keyboard shortcuts:**
| Key | Action |
|-----|--------|
| Left/Right arrows | Previous/next group |
| S | Skip this group |
| M | Mark dupes for move |
| D | Mark dupes for delete |
| Escape | Close image zoom |

**Toolbar features:**
- **Sort by**: default order, file size, reclaimable space, or distance
- **Filter**: show all, unreviewed only, or filter by your decision (move/delete/skip)
- **Search**: type a filename or folder name to find specific groups
- **Bulk actions**: Mark All for Move, Skip All
- **Click any image** to zoom in (lightbox view)

### Execute Actions

After reviewing, go to the **Actions** page to carry out your decisions:
- Shows a summary: how many files to move, how many to delete, total space to reclaim
- **Move destination**: enter the folder where dupes should be moved (e.g. `C:\Temp\dupes`)
- Click **Execute** and confirm in the dialog
- Watch real-time progress as files are moved/deleted
- Any errors are listed with the reason (locked file, permission denied, etc.)

### Oddball Verification

After moving duplicates, you can double-check for false positives:
1. Go to the **Oddball** page
2. Enter the folder where dupes were moved
3. Click **Run Verification**
4. DupeFinder re-hashes each KEEP/DUPE pair and flags weak matches (high distance)
5. Review flagged pairs -- if something was wrongly marked as a dupe, click **Rescue** to move it back

### Settings

Customize defaults that persist between sessions:
- **Threshold**: default perceptual similarity threshold (0-20)
- **Move destination**: default folder for moving dupes
- **Keep strategy**: how to pick which file to keep in each group
  - Largest file (default) -- keeps the highest quality version
  - Oldest file -- keeps the original by date
  - Newest file -- keeps the most recent version
  - Shortest filename -- keeps the cleanest name
- **Extensions**: which file types to scan (comma-separated)
- **Port**: server port (default 8787)

---

## Important Notes

### OneDrive
Your Pictures folder syncs via OneDrive. Before running bulk move or delete operations:
- **Pause OneDrive sync** (right-click the OneDrive icon in the system tray > Pause syncing)
- Run your operations
- Resume sync afterward
- If OneDrive pops up asking to "Keep" restored files, click **No** or it will undo your cleanup

### File Safety
- DupeFinder uses **copy + delete** (not move) to avoid OneDrive file locking issues
- Each file operation is independent -- one failure won't stop the rest
- Failed files are logged and shown in the UI
- Move operations are reversible: files go to your chosen destination folder, not the recycle bin
- **Delete operations are permanent** -- files are not sent to the recycle bin

### Controlled Folder Access
Windows Defender's Controlled Folder Access is enabled on this machine. If the app can't create files, make sure `C:\Program Files\Python313\python.exe` is whitelisted:
- Open **Windows Security** > **Virus & threat protection** > **Ransomware protection**
- Click **Allow an app through Controlled folder access**
- Add the Python executable

---

## Troubleshooting

| Problem | Solution |
|---------|----------|
| Browser doesn't open | Navigate manually to `http://127.0.0.1:8787` |
| "Address already in use" | Another instance is running. Close it or change the port in Settings |
| Images don't load | Check that the image files still exist at their original paths |
| "Access denied" on file operations | Pause OneDrive sync, check Controlled Folder Access |
| Scan seems stuck | Check the progress bar -- perceptual scans on large folders take time. You can cancel and try exact-only |
| Server won't start | Make sure Python 3.13 is being used, not 3.14 |

# DupeFinder Testing Tracker

Track file counts, scan results, and test outcomes for consistency across sessions.

---

## Test Environment

- **OS:** Windows 11 Home
- **Python:** 3.13 (system), pywebview native window
- **Source folder:** OneDrive Pictures
- **RAM:** 32GB, GPU: GeForce GTX (12GB VRAM)

---

## Session Log

### Session: 2026-03-21

| Step | Files In | Files Out | Groups | Duration | Notes |
|------|----------|-----------|--------|----------|-------|
| Migration | 22,777 source | 22,777 staged | -- | ~30-45 min (cloud-only) | OneDrive downloaded files from cloud |
| Scan (both, t=5, all) | 22,114 | -- | 6,738 | 18.5 min | Full scan, LSH bucketing |
| Scan (both, t=5, 2000) | 2,000 | -- | 501 | 1:28 | Batch scan working |
| Scan (both, t=20, all) | 22,777 | -- | 6,848 | 19.1 min | High threshold, many groups |

### Session: 2026-03-22

| Step | Files In | Files Out | Groups | Duration | Notes |
|------|----------|-----------|--------|----------|-------|
| Scan (both, t=5, 2000) | 2,000 | 475 moved | 501 | 1:28 | Batch scan + execute |
| Scan keepers (both, t=5) | 70 | 0 | 0 | 1.1s | Small folder, fast |
| Scan dupes (both, t=5) | 248 | 0 | 0 | ~15s | No dupes in dupes folder |

---

## Known File Count Checkpoints

Use these to verify file integrity after operations:

| Checkpoint | My Files | Removed Dupes | Verified Keepers | Total |
|------------|----------|---------------|------------------|-------|
| After migration | 22,777 | 0 | 0 | 22,777 |
| After first scan+execute | ~17,000 | ~5,700 | 0 | 22,777 |
| After Send Files Home | 0 | 0 | 0 | 0 (all returned) |

**Rule:** Total files across all system folders should always equal the migration count (minus any recycled files).

---

## Test Checklist Template

Copy for each test session:

- [ ] App launches cleanly (single window, no console)
- [ ] Dashboard shows correct file counts
- [ ] Stepper reflects current workflow state
- [ ] Scan config: batch size, threshold, mode all work
- [ ] Scan completes without errors
- [ ] Review: navigate groups, mark as dupe/keep works
- [ ] Mark All Remaining shows dialog and updates counter
- [ ] Apply Decisions shows correct file counts
- [ ] Execute moves files, dashboard updates
- [ ] Send Files Home returns all files
- [ ] Tooltips appear on hover (when enabled)
- [ ] Persistent logging toggle works (Ctrl+Shift+F5)
- [ ] Key combos don't interfere with operations
- [ ] Recovery archive appears after recycle operations
- [ ] Window resize: layout adjusts, no content overflow

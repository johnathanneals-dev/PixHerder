"""
DupeFinder oddball verification.
Re-hashes KEEP/DUPE pairs and flags weak matches as potential false positives.
"""

import os
from pathlib import Path

from engine.hasher import perceptual_hash


def verify_pairs(report_data, dupes_folder=None, progress_cb=None,
                 cancel_event=None):
    """Re-hash keep/dupe pairs and compute actual distances.

    Args:
        report_data: List of group dicts with "keep" and "duplicates" keys.
        dupes_folder: Optional folder where dupes were moved to. If a dupe
                      is not found at its original path, looks here.
        progress_cb: Optional callback(current, total, stage).
        cancel_event: Optional threading.Event for cancellation.

    Returns:
        Dict with results (list sorted by distance desc), errors (list),
        checked (int), skipped (int), cancelled (bool).
    """
    results = []
    errors = []
    checked = 0
    skipped = 0
    cancelled = False

    total_dupes = sum(len(g.get("duplicates", [])) for g in report_data)

    for group in report_data:
        if cancel_event and cancel_event.is_set():
            cancelled = True
            break

        keep_path = group.get("keep", "")

        if not os.path.isfile(keep_path):
            skipped += len(group.get("duplicates", []))
            checked += len(group.get("duplicates", []))
            if progress_cb:
                progress_cb(checked, total_dupes, "oddball")
            continue

        keep_hash, err = perceptual_hash(keep_path)
        if err:
            errors.append({"path": keep_path, "error": err})
        if keep_hash is None:
            skipped += len(group.get("duplicates", []))
            checked += len(group.get("duplicates", []))
            if progress_cb:
                progress_cb(checked, total_dupes, "oddball")
            continue

        for dupe_path in group.get("duplicates", []):
            if cancel_event and cancel_event.is_set():
                cancelled = True
                break

            checked += 1
            actual_path = dupe_path

            # Try to find the file
            if not os.path.isfile(actual_path) and dupes_folder:
                fname = os.path.basename(dupe_path)
                moved_path = os.path.join(dupes_folder, fname)
                if os.path.isfile(moved_path):
                    actual_path = moved_path
                else:
                    skipped += 1
                    if progress_cb:
                        progress_cb(checked, total_dupes, "oddball")
                    continue

            if not os.path.isfile(actual_path):
                skipped += 1
                if progress_cb:
                    progress_cb(checked, total_dupes, "oddball")
                continue

            dupe_hash, err = perceptual_hash(actual_path)
            if err:
                errors.append({"path": actual_path, "error": err})
            if dupe_hash is None:
                skipped += 1
                if progress_cb:
                    progress_cb(checked, total_dupes, "oddball")
                continue

            distance = keep_hash - dupe_hash

            results.append({
                "distance": distance,
                "keep": keep_path,
                "dupe": actual_path,
                "original_dupe_path": dupe_path,
            })

            if progress_cb:
                progress_cb(checked, total_dupes, "oddball")

        if cancelled:
            break

    # Sort by distance descending (most suspicious first)
    results.sort(key=lambda x: x["distance"], reverse=True)

    return {
        "results": results,
        "errors": errors,
        "checked": checked,
        "skipped": skipped,
        "cancelled": cancelled,
    }


def filter_oddballs(results, min_distance=6):
    """Filter verification results to only suspicious pairs.

    Args:
        results: List of dicts from verify_pairs.
        min_distance: Minimum distance to flag as oddball (default 6).

    Returns:
        List of group dicts in standard report format with distance field.
    """
    groups = []
    for r in results:
        if r["distance"] >= min_distance:
            dupe_path = r["dupe"]
            try:
                size = os.path.getsize(dupe_path)
            except Exception:
                size = 0

            groups.append({
                "keep": r["keep"],
                "duplicates": [dupe_path],
                "reclaimable_bytes": size,
                "distance": r["distance"],
                "original_dupe_path": r["original_dupe_path"],
            })
    return groups

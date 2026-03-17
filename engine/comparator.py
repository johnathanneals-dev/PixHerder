"""
DupeFinder duplicate detection and grouping logic.
Groups images by exact match (MD5) or visual similarity (pHash).
"""

from collections import defaultdict
from pathlib import Path

from engine.hasher import md5_hash, perceptual_hash


def find_exact_duplicates(image_paths, progress_cb=None, cancel_event=None):
    """Group images by identical MD5 hash.

    Args:
        image_paths: List of Path objects.
        progress_cb: Optional callback(current, total, stage).
        cancel_event: Optional threading.Event for cancellation.

    Returns:
        Dict with keys: groups (list of lists of paths), errors (list),
        cancelled (bool).
    """
    hash_map = defaultdict(list)
    errors = []
    total = len(image_paths)
    cancelled = False

    for i, path in enumerate(image_paths):
        if cancel_event and cancel_event.is_set():
            cancelled = True
            break

        digest, err = md5_hash(path)
        if err:
            errors.append({"path": str(path), "error": err})
        if digest is not None:
            hash_map[digest].append(path)

        if progress_cb:
            progress_cb(i + 1, total, "md5")

    groups = [v for v in hash_map.values() if len(v) > 1]
    return {"groups": groups, "errors": errors, "cancelled": cancelled}


def find_perceptual_duplicates(image_paths, threshold=5, hash_size=16,
                               progress_cb=None, cancel_event=None):
    """Group images by perceptual similarity within a hamming distance threshold.

    Two phases: hashing (I/O bound) then comparison (CPU bound).

    Args:
        image_paths: List of Path objects.
        threshold: Max hamming distance to consider a match (0-20).
        hash_size: Hash size for pHash (default 16).
        progress_cb: Optional callback(current, total, stage).
        cancel_event: Optional threading.Event for cancellation.

    Returns:
        Dict with keys: groups (list of dicts with keep/duplicates/distances),
        errors (list), cancelled (bool).
    """
    hashes = []
    errors = []
    total = len(image_paths)
    cancelled = False

    # Phase 1: compute all perceptual hashes
    for i, path in enumerate(image_paths):
        if cancel_event and cancel_event.is_set():
            return {"groups": [], "errors": errors, "cancelled": True}

        h, err = perceptual_hash(path, hash_size=hash_size)
        if err:
            errors.append({"path": str(path), "error": err})
        if h is not None:
            hashes.append((path, h))

        if progress_cb:
            progress_cb(i + 1, total, "phash_hash")

    # Phase 2: cluster by similarity (O(n^2))
    n = len(hashes)
    total_comparisons = (n * (n - 1)) // 2 if n > 1 else 0
    comparisons_done = 0
    used = set()
    groups = []

    for i in range(n):
        if i in used:
            continue
        if cancel_event and cancel_event.is_set():
            cancelled = True
            break

        path_a, hash_a = hashes[i]
        group = [path_a]
        distances = {}
        used.add(i)

        for j in range(i + 1, n):
            if j in used:
                comparisons_done += 1
                continue

            path_b, hash_b = hashes[j]
            distance = hash_a - hash_b  # hamming distance

            if distance <= threshold:
                group.append(path_b)
                distances[str(path_b)] = distance
                used.add(j)

            comparisons_done += 1

        if progress_cb and comparisons_done % 5000 == 0:
            progress_cb(comparisons_done, total_comparisons, "phash_compare")

        if len(group) > 1:
            groups.append({
                "paths": group,
                "distances": distances,
            })

    # Send final progress for comparison phase
    if progress_cb and total_comparisons > 0:
        progress_cb(total_comparisons, total_comparisons, "phash_compare")

    return {"groups": groups, "errors": errors, "cancelled": cancelled}


def pick_original(group, strategy="largest"):
    """Pick the best file to keep from a group of duplicates.

    Args:
        group: List of Path objects (or strings).
        strategy: One of "largest", "oldest", "newest", "shortest_name".

    Returns:
        Path object of the file to keep, or None if no valid files remain.
    """
    valid = []
    for p in group:
        p = Path(p)
        try:
            stat = p.stat()
            valid.append((p, stat))
        except Exception:
            continue

    if not valid:
        return None

    if strategy == "largest":
        return max(valid, key=lambda x: x[1].st_size)[0]
    elif strategy == "oldest":
        return min(valid, key=lambda x: x[1].st_mtime)[0]
    elif strategy == "newest":
        return max(valid, key=lambda x: x[1].st_mtime)[0]
    elif strategy == "shortest_name":
        return min(valid, key=lambda x: len(x[0].name))[0]
    else:
        return max(valid, key=lambda x: x[1].st_size)[0]

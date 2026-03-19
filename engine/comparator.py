"""
DupeFinder duplicate detection and grouping logic.
Groups images by exact match (MD5) or visual similarity (pHash).
"""

import os
from collections import defaultdict
from pathlib import Path

from engine.hasher import md5_hash, perceptual_hash


def find_exact_duplicates(image_paths, progress_cb=None, cancel_event=None,
                          precomputed_hashes=None, checkpoint_cb=None,
                          batch_size=500):
    """Group images by identical MD5 hash.

    Args:
        image_paths: List of Path objects.
        progress_cb: Optional callback(current, total, stage).
        cancel_event: Optional threading.Event for cancellation.
        precomputed_hashes: Optional dict {filepath_str: md5_hex} to skip rehashing.
        checkpoint_cb: Optional callback(hashes_dict, file_info_dict) for saving state.

    Returns:
        Dict with keys: groups (list of lists of paths), errors (list),
        cancelled (bool), hashes (dict of computed hashes), file_info (dict).
    """
    hash_map = defaultdict(list)
    errors = []
    total = len(image_paths)
    cancelled = False
    computed_hashes = dict(precomputed_hashes or {})
    file_info = {}

    for i, path in enumerate(image_paths):
        if cancel_event and cancel_event.is_set():
            cancelled = True
            break

        path_str = str(path)
        if path_str in computed_hashes:
            # Use cached hash
            digest = computed_hashes[path_str]
            hash_map[digest].append(path)
        else:
            digest, err = md5_hash(path)
            if err:
                errors.append({"path": path_str, "error": err})
            if digest is not None:
                hash_map[digest].append(path)
                computed_hashes[path_str] = digest
                try:
                    st = os.stat(path_str)
                    file_info[path_str] = {"mtime": st.st_mtime, "size": st.st_size}
                except Exception:
                    pass

        if progress_cb:
            progress_cb(i + 1, total, "md5")

        if checkpoint_cb and (i + 1) % batch_size == 0:
            checkpoint_cb(computed_hashes, file_info)

    groups = [v for v in hash_map.values() if len(v) > 1]
    return {
        "groups": groups,
        "errors": errors,
        "cancelled": cancelled,
        "hashes": computed_hashes,
        "file_info": file_info,
    }


def find_perceptual_duplicates(image_paths, threshold=5, hash_size=16,
                               progress_cb=None, cancel_event=None,
                               precomputed_hashes=None, checkpoint_cb=None,
                               batch_size=500):
    """Group images by perceptual similarity within a hamming distance threshold.

    Two phases: hashing (I/O bound) then comparison (CPU bound).

    Args:
        image_paths: List of Path objects.
        threshold: Max hamming distance to consider a match (0-20).
        hash_size: Hash size for pHash (default 16).
        progress_cb: Optional callback(current, total, stage).
        cancel_event: Optional threading.Event for cancellation.
        precomputed_hashes: Optional dict {filepath_str: hash_hex_str} to skip rehashing.
        checkpoint_cb: Optional callback(hashes_dict, file_info_dict) for saving state.

    Returns:
        Dict with keys: groups (list of dicts with keep/duplicates/distances),
        errors (list), cancelled (bool), hashes (dict), file_info (dict).
    """
    import imagehash
    from PIL import Image as PILImage

    hashes = []
    errors = []
    total = len(image_paths)
    cancelled = False
    computed_hashes = dict(precomputed_hashes or {})
    file_info = {}

    # Phase 1: compute all perceptual hashes
    for i, path in enumerate(image_paths):
        if cancel_event and cancel_event.is_set():
            return {
                "groups": [], "errors": errors, "cancelled": True,
                "hashes": computed_hashes, "file_info": file_info,
            }

        path_str = str(path)
        if path_str in computed_hashes:
            # Reconstruct hash object from hex string
            try:
                h = imagehash.hex_to_hash(computed_hashes[path_str])
                hashes.append((path, h))
            except Exception:
                # Stored hash is corrupt, recompute
                computed_hashes.pop(path_str, None)
                h, err = perceptual_hash(path, hash_size=hash_size)
                if err:
                    errors.append({"path": path_str, "error": err})
                if h is not None:
                    hashes.append((path, h))
                    computed_hashes[path_str] = str(h)
        else:
            h, err = perceptual_hash(path, hash_size=hash_size)
            if err:
                errors.append({"path": path_str, "error": err})
            if h is not None:
                hashes.append((path, h))
                computed_hashes[path_str] = str(h)
                try:
                    st = os.stat(path_str)
                    file_info[path_str] = {"mtime": st.st_mtime, "size": st.st_size}
                except Exception:
                    pass

        if progress_cb:
            progress_cb(i + 1, total, "phash_hash")

        if checkpoint_cb and (i + 1) % batch_size == 0:
            checkpoint_cb(computed_hashes, file_info)

    # Phase 2: cluster by similarity (O(n^2))
    n = len(hashes)
    total_comparisons = (n * (n - 1)) // 2 if n > 1 else 0
    comparisons_done = 0
    used = set()
    groups = []
    # Report progress roughly every 1% (min every 500 comparisons)
    report_interval = max(500, total_comparisons // 100) if total_comparisons > 0 else 1
    last_reported = 0

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
            distance = int(hash_a - hash_b)  # hamming distance

            if distance <= threshold:
                group.append(path_b)
                distances[str(path_b)] = distance
                used.add(j)

            comparisons_done += 1

        if progress_cb and (comparisons_done - last_reported) >= report_interval:
            progress_cb(comparisons_done, total_comparisons, "phash_compare")
            last_reported = comparisons_done

        if len(group) > 1:
            groups.append({
                "paths": group,
                "distances": distances,
            })

    # Send final progress for comparison phase
    if progress_cb and total_comparisons > 0:
        progress_cb(total_comparisons, total_comparisons, "phash_compare")

    return {
        "groups": groups,
        "errors": errors,
        "cancelled": cancelled,
        "hashes": computed_hashes,
        "file_info": file_info,
    }


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

"""
DupeFinder duplicate detection and grouping logic.
Groups images by exact match (MD5) or visual similarity (pHash).
"""

import logging
import os
from collections import defaultdict
from pathlib import Path

from engine.hasher import md5_hash, perceptual_hash

logger = logging.getLogger(__name__)


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
    logger.info("Starting exact duplicate scan on %d images", total)
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
    logger.info("Found %d exact duplicate groups", len(groups))
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
    logger.info("Starting perceptual scan: %d images, threshold=%d", total, threshold)
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

    # Phase 2: cluster by similarity
    # Use bit-prefix bucketing to reduce comparisons.
    # Images are placed in multiple buckets based on hash bit segments.
    # Only images sharing at least one bucket are compared, dramatically
    # reducing the search space for large collections.
    n = len(hashes)
    used = set()
    groups = []

    if n > 500 and threshold <= 20:
        # Multi-probe bucketing: split hash bits into bands, bucket by band
        # Each band of k bits can differ by at most threshold/num_bands bits
        # for a match, so items in the same bucket are candidates.
        # Build candidate pairs using bit sampling
        # Use 4 bands of the hash — items must match in at least one band
        num_bands = 4
        hash_hex_len = len(str(hashes[0][1]))
        chars_per_band = max(1, hash_hex_len // num_bands)

        buckets = [defaultdict(list) for _ in range(num_bands)]
        for idx, (_, h) in enumerate(hashes):
            h_str = str(h)
            for band in range(num_bands):
                start = band * chars_per_band
                end = start + chars_per_band
                key = h_str[start:end]
                buckets[band][key].append(idx)

        # Collect candidate pairs from buckets
        candidate_pairs = set()
        for band_buckets in buckets:
            for members in band_buckets.values():
                if len(members) > 1:
                    for ii in range(len(members)):
                        for jj in range(ii + 1, len(members)):
                            a, b = members[ii], members[jj]
                            if a < b:
                                candidate_pairs.add((a, b))
                            else:
                                candidate_pairs.add((b, a))

        logger.debug("LSH bucketing: %d candidate pairs from %d images", len(candidate_pairs), n)
        total_comparisons = len(candidate_pairs)
        comparisons_done = 0
        report_interval = max(500, total_comparisons // 100) if total_comparisons > 0 else 1
        last_reported = 0

        # Union-Find for order-independent clustering
        parent = list(range(n))
        uf_rank = [0] * n

        def find(x):
            while parent[x] != x:
                parent[x] = parent[parent[x]]
                x = parent[x]
            return x

        def union(x, y):
            px, py = find(x), find(y)
            if px == py:
                return
            if uf_rank[px] < uf_rank[py]:
                px, py = py, px
            parent[py] = px
            if uf_rank[px] == uf_rank[py]:
                uf_rank[px] += 1

        # Compare candidate pairs and union matches
        for i_idx, j_idx in candidate_pairs:
            if cancel_event and cancel_event.is_set():
                cancelled = True
                break

            distance = int(hashes[i_idx][1] - hashes[j_idx][1])
            if distance <= threshold:
                union(i_idx, j_idx)

            comparisons_done += 1
            if progress_cb and (comparisons_done - last_reported) >= report_interval:
                progress_cb(comparisons_done, total_comparisons, "phash_compare")
                last_reported = comparisons_done

        # Collect groups from Union-Find
        if not cancelled:
            group_map = defaultdict(list)
            for i in range(n):
                group_map[find(i)].append(i)

            for root, members in group_map.items():
                if len(members) > 1:
                    paths = [hashes[m][0] for m in members]
                    dists = {}
                    for m in members[1:]:
                        d = int(hashes[members[0]][1] - hashes[m][1])
                        dists[str(hashes[m][0])] = d
                    groups.append({"paths": paths, "distances": dists})

    else:
        # Small collection — brute force O(n^2) is fine
        total_comparisons = (n * (n - 1)) // 2 if n > 1 else 0
        comparisons_done = 0
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
                distance = int(hash_a - hash_b)

                if distance <= threshold:
                    group.append(path_b)
                    distances[str(path_b)] = distance
                    used.add(j)

                comparisons_done += 1

            if progress_cb and (comparisons_done - last_reported) >= report_interval:
                progress_cb(comparisons_done, total_comparisons, "phash_compare")
                last_reported = comparisons_done

            if len(group) > 1:
                groups.append({"paths": group, "distances": distances})

    logger.info("Found %d perceptual groups", len(groups))

    # Send final progress for comparison phase
    if progress_cb:
        progress_cb(1, 1, "phash_compare")

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

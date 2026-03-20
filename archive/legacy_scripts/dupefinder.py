#!/usr/bin/env python3
"""
DupeFinder - A customizable duplicate image finder.
Finds duplicate and near-duplicate images using multiple strategies.

Usage:
    python dupefinder.py /path/to/photos
    python dupefinder.py /path/to/photos --threshold 10 --action report
    python dupefinder.py /path/to/photos --action move --move-dir ./dupes

Strategies:
    1. Exact match   - MD5 hash (byte-identical files)
    2. Perceptual    - pHash (visually similar, even if resized/recompressed)
    3. File size     - groups files with identical sizes (quick pre-filter)
"""

import os
import sys
import hashlib
import argparse
import json
import shutil
from pathlib import Path
from datetime import datetime
from collections import defaultdict

from PIL import Image
import imagehash


# ----------------------------------------------
#  CONFIG - tweak these to your liking
# ----------------------------------------------
SUPPORTED_EXTENSIONS = {
    ".jpg", ".jpeg", ".png", ".gif", ".bmp",
    ".tiff", ".tif", ".webp", ".heic", ".heif",
}

# Perceptual hash threshold: 0 = exact visual match, higher = more lenient.
# Recommended: 0-5 for near-duplicates, 6-12 for similar images.
DEFAULT_THRESHOLD = 5

# Hash size for perceptual hashing (larger = more precise but slower)
HASH_SIZE = 16


# ----------------------------------------------
#  SCANNING
# ----------------------------------------------
def find_images(directory, recursive=True):
    """Walk a directory and yield all image file paths."""
    directory = Path(directory)
    pattern = "**/*" if recursive else "*"
    for filepath in directory.glob(pattern):
        if filepath.is_file() and filepath.suffix.lower() in SUPPORTED_EXTENSIONS:
            yield filepath


# ----------------------------------------------
#  HASHING
# ----------------------------------------------
def md5_hash(filepath):
    """Return the MD5 hex digest of a file."""
    try:
        h = hashlib.md5()
        with open(filepath, "rb") as f:
            for chunk in iter(lambda: f.read(8192), b""):
                h.update(chunk)
        return h.hexdigest()
    except Exception as e:
        print(f"\n  [!] Could not read {filepath}: {e}")
        return None


def perceptual_hash(filepath, hash_size=HASH_SIZE):
    """Return the perceptual hash (pHash) of an image."""
    try:
        img = Image.open(filepath)
        return imagehash.phash(img, hash_size=hash_size)
    except Exception as e:
        print(f"  [!] Could not hash {filepath}: {e}")
        return None


# ----------------------------------------------
#  DUPLICATE DETECTION
# ----------------------------------------------
def find_exact_duplicates(image_paths):
    """Group images by identical MD5 hash (byte-for-byte dupes)."""
    hash_map = defaultdict(list)
    total = len(image_paths)

    for i, path in enumerate(image_paths, 1):
        print(f"\r  Hashing (MD5): {i}/{total}", end="", flush=True)
        digest = md5_hash(path)
        if digest is not None:
            hash_map[digest].append(path)

    print()
    return {k: v for k, v in hash_map.items() if len(v) > 1}


def find_perceptual_duplicates(image_paths, threshold=DEFAULT_THRESHOLD):
    """Group images by perceptual similarity within a hamming distance threshold."""
    hashes = []
    total = len(image_paths)

    # Step 1: compute all perceptual hashes
    for i, path in enumerate(image_paths, 1):
        print(f"\r  Hashing (pHash): {i}/{total}", end="", flush=True)
        h = perceptual_hash(path)
        if h is not None:
            hashes.append((path, h))
    print()

    # Step 2: cluster by similarity
    used = set()
    groups = []

    for i, (path_a, hash_a) in enumerate(hashes):
        if i in used:
            continue
        group = [path_a]
        used.add(i)

        for j, (path_b, hash_b) in enumerate(hashes):
            if j in used:
                continue
            distance = hash_a - hash_b  # hamming distance
            if distance <= threshold:
                group.append(path_b)
                used.add(j)

        if len(group) > 1:
            groups.append(group)

    return groups


# ----------------------------------------------
#  CHOOSING WHICH FILE TO KEEP
# ----------------------------------------------
def pick_original(group):
    """
    Given a group of duplicate files, pick the 'best' one to keep.
    Current strategy: keep the largest file (likely highest quality).

    Modify this to change the keep logic! Ideas:
        - Keep oldest file (earliest mtime)
        - Keep the one with the shortest filename
        - Keep the one in a specific folder
    """
    valid = []
    for p in group:
        try:
            size = p.stat().st_size
            valid.append((p, size))
        except Exception:
            continue
    if not valid:
        return None
    return max(valid, key=lambda x: x[1])[0]


# ----------------------------------------------
#  ACTIONS
# ----------------------------------------------
def action_report(groups, label="Duplicate"):
    """Print a human-readable report of duplicate groups."""
    total_waste = 0
    for i, group in enumerate(groups, 1):
        original = pick_original(group)
        dupes = [p for p in group if p != original]
        waste = sum(p.stat().st_size for p in dupes)
        total_waste += waste

        print(f"\n-- {label} Group {i} ({len(group)} files) --")
        print(f"  [KEEP] {original}  ({original.stat().st_size:,} bytes)")
        for d in dupes:
            print(f"  [DUPE] {d}  ({d.stat().st_size:,} bytes)")

    mb = total_waste / (1024 * 1024)
    print(f"\n{'-' * 50}")
    print(f"  Total duplicate groups: {len(groups)}")
    print(f"  Space reclaimable:      {mb:.1f} MB")
    return groups


def action_move(groups, move_dir):
    """Move duplicate files to a separate directory (safe - nothing deleted).
    Uses copy+delete instead of move for OneDrive compatibility."""
    move_dir = Path(move_dir)
    os.makedirs(str(move_dir), exist_ok=True)
    moved = 0
    errors = 0

    for group in groups:
        original = pick_original(group)
        if original is None:
            continue
        for path in group:
            if path == original:
                continue
            dest = move_dir / path.name
            # avoid overwriting in the dupes folder
            if dest.exists():
                stem = dest.stem
                dest = move_dir / f"{stem}_{moved}{dest.suffix}"
            try:
                shutil.copy2(str(path), str(dest))
                os.remove(str(path))
                moved += 1
                print(f"  Moved: {path.name} -> {move_dir}/")
            except Exception as e:
                errors += 1
                print(f"  [!] Failed: {path.name} - {e}")

    print(f"\n  Moved {moved} duplicate(s) to {move_dir}")
    if errors:
        print(f"  [!] {errors} file(s) could not be moved (OneDrive locked?)")


def action_delete(groups):
    """DELETE duplicate files. Use with caution!"""
    deleted = 0
    for group in groups:
        original = pick_original(group)
        for path in group:
            if path == original:
                continue
            print(f"  Deleting: {path}")
            path.unlink()
            deleted += 1
    print(f"\n  Deleted {deleted} file(s)")


def action_json(groups, output_file="dupes_report.json"):
    """Export results to JSON for further processing."""
    data = []
    for group in groups:
        original = pick_original(group)
        data.append({
            "keep": str(original),
            "duplicates": [str(p) for p in group if p != original],
            "files": len(group),
            "reclaimable_bytes": sum(
                p.stat().st_size for p in group if p != original
            ),
        })
    output_path = Path(output_file)
    os.makedirs(str(output_path.parent), exist_ok=True)
    with open(str(output_path), "w") as f:
        json.dump(data, f, indent=2)
    print(f"  Report saved to {output_file}")


# ----------------------------------------------
#  MAIN
# ----------------------------------------------
def main():
    parser = argparse.ArgumentParser(
        description="DupeFinder - Find duplicate images fast.",
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    parser.add_argument("directory", help="Folder to scan for duplicate images")
    parser.add_argument(
        "--mode", choices=["exact", "perceptual", "both"], default="both",
        help="Detection mode (default: both)"
    )
    parser.add_argument(
        "--threshold", type=int, default=DEFAULT_THRESHOLD,
        help=f"Perceptual similarity threshold 0-20 (default: {DEFAULT_THRESHOLD})"
    )
    parser.add_argument(
        "--action", choices=["report", "move", "delete", "json"], default="report",
        help="What to do with found duplicates (default: report)"
    )
    parser.add_argument(
        "--move-dir", default="./duplicates",
        help="Directory to move dupes into (used with --action move)"
    )
    parser.add_argument(
        "--no-recursive", action="store_true",
        help="Don't scan subdirectories"
    )
    parser.add_argument(
        "--json-out", default="dupes_report.json",
        help="Output file for JSON report"
    )
    args = parser.parse_args()

    directory = Path(args.directory)
    if not directory.is_dir():
        print(f"[ERROR] Not a directory: {directory}")
        sys.exit(1)

    print(f"\nDupeFinder - Scanning: {directory}")
    print(f"  Mode: {args.mode} | Threshold: {args.threshold} | Action: {args.action}\n")

    # Collect all images
    image_paths = list(find_images(directory, recursive=not args.no_recursive))
    print(f"  Found {len(image_paths)} images\n")

    if len(image_paths) < 2:
        print("  Not enough images to compare. Done!")
        sys.exit(0)

    all_groups = []

    # Exact duplicates
    if args.mode in ("exact", "both"):
        print("== Stage 1: Exact (MD5) duplicates ==")
        exact = find_exact_duplicates(image_paths)
        exact_groups = list(exact.values())
        if exact_groups:
            action_report(exact_groups, label="Exact")
        else:
            print("  No exact duplicates found.")
        all_groups.extend(exact_groups)

    # Perceptual duplicates
    if args.mode in ("perceptual", "both"):
        print("\n== Stage 2: Perceptual (visual) duplicates ==")
        perceptual_groups = find_perceptual_duplicates(image_paths, args.threshold)
        if perceptual_groups:
            action_report(perceptual_groups, label="Perceptual")
        else:
            print("  No perceptual duplicates found.")
        all_groups.extend(perceptual_groups)

    # Perform chosen action
    if all_groups and args.action != "report":
        print(f"\n== Performing action: {args.action} ==")
        if args.action == "move":
            action_move(all_groups, args.move_dir)
        elif args.action == "delete":
            confirm = input("  WARNING: Type YES to confirm deletion: ")
            if confirm == "YES":
                action_delete(all_groups)
            else:
                print("  Aborted.")
        elif args.action == "json":
            action_json(all_groups, args.json_out)

    print("\nDone!\n")


if __name__ == "__main__":
    main()

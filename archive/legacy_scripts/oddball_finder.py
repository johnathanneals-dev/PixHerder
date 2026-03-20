#!/usr/bin/env python3
"""
OddballFinder - Checks moved dupes against their KEEP files.
Flags any pairs where the perceptual similarity is weak (possible false positives).

Usage:
    python oddball_finder.py
"""

import json
import sys
import os
from pathlib import Path
from PIL import Image
import imagehash

HASH_SIZE = 16
REPORT_FILE = "perceptual_report.json"


def perceptual_hash(filepath, hash_size=HASH_SIZE):
    try:
        img = Image.open(filepath)
        return imagehash.phash(img, hash_size=hash_size)
    except Exception as e:
        return None


def main():
    if not os.path.exists(REPORT_FILE):
        print("[ERROR] Cannot find " + REPORT_FILE)
        sys.exit(1)

    with open(REPORT_FILE) as f:
        groups = json.load(f)

    print("")
    print("OddballFinder - Checking dupes against originals")
    print("  Groups to check: " + str(len(groups)))
    print("")

    results = []
    checked = 0
    skipped = 0
    total_dupes = sum(len(g["duplicates"]) for g in groups)

    for gi, group in enumerate(groups):
        keep_path = group["keep"]

        if not os.path.isfile(keep_path):
            skipped += 1
            continue

        keep_hash = perceptual_hash(keep_path)
        if keep_hash is None:
            skipped += 1
            continue

        for dupe_path in group["duplicates"]:
            checked += 1
            if checked % 100 == 0:
                print("\r  Checking: " + str(checked) + "/" + str(total_dupes), end="", flush=True)

            # Check if dupe still exists in original location or was moved
            actual_path = dupe_path
            if not os.path.isfile(actual_path):
                # Try the moved location
                fname = os.path.basename(dupe_path)
                moved_path = os.path.join("C:\\Temp\\perceptual_dupes", fname)
                if os.path.isfile(moved_path):
                    actual_path = moved_path
                else:
                    skipped += 1
                    continue

            dupe_hash = perceptual_hash(actual_path)
            if dupe_hash is None:
                skipped += 1
                continue

            distance = keep_hash - dupe_hash

            results.append({
                "distance": distance,
                "keep": keep_path,
                "dupe": actual_path,
                "original_dupe_path": dupe_path,
            })

    print("\r  Checked: " + str(checked) + "/" + str(total_dupes) + "          ")
    print("  Skipped: " + str(skipped))
    print("")

    # Sort by distance (highest = least similar = most likely oddball)
    results.sort(key=lambda x: x["distance"], reverse=True)

    # Show summary by distance brackets
    brackets = {}
    for r in results:
        d = r["distance"]
        if d == 0:
            b = "0 (identical)"
        elif d <= 2:
            b = "1-2 (very close)"
        elif d <= 5:
            b = "3-5 (near duplicate)"
        elif d <= 10:
            b = "6-10 (similar)"
        else:
            b = "11+ (ODDBALL - review these!)"
        if b not in brackets:
            brackets[b] = 0
        brackets[b] += 1

    print("  Distance breakdown:")
    print("  " + "-" * 45)
    for b in ["0 (identical)", "1-2 (very close)", "3-5 (near duplicate)", "6-10 (similar)", "11+ (ODDBALL - review these!)"]:
        if b in brackets:
            print("    " + b + ": " + str(brackets[b]) + " files")
    print("")

    # Save oddballs (distance > 5) to a separate JSON
    oddballs = [r for r in results if r["distance"] > 5]

    if oddballs:
        print("  Found " + str(len(oddballs)) + " potential oddballs (distance > 5)")
        print("  Saving to oddballs_report.json ...")

        oddball_groups = []
        for o in oddballs:
            oddball_groups.append({
                "keep": o["keep"],
                "duplicates": [o["dupe"]],
                "reclaimable_bytes": os.path.getsize(o["dupe"]) if os.path.isfile(o["dupe"]) else 0,
                "distance": o["distance"],
            })

        with open("oddballs_report.json", "w") as f:
            json.dump(oddball_groups, f, indent=2)

        print("  Done! Review these with:")
        print("    python reviewer.py --report oddballs_report.json")
        print("")
        print("  Top 20 most suspicious pairs:")
        print("  " + "-" * 45)
        for o in oddballs[:20]:
            print("    Distance " + str(o["distance"]) + ":")
            print("      KEEP: " + o["keep"])
            print("      DUPE: " + o["dupe"])
            print("")
    else:
        print("  No oddballs found! All dupes look like genuine matches.")

    print("Done!")


if __name__ == "__main__":
    main()
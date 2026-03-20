#!/usr/bin/env python3
"""
final_sort.py - Separate the 258 close/near-duplicate files for review,
and delete the confirmed identical ones.

Reads perceptual_report.json, re-hashes each pair, then:
  - Distance 0: delete from C:\Temp\perceptual_dupes (confirmed dupe)
  - Distance 1-5: copy to C:\Projects\Duped\final_review for one last look
"""

import json
import os
import sys
import shutil
from PIL import Image
import imagehash

HASH_SIZE = 16
REPORT_FILE = "perceptual_report.json"
DUPES_FOLDER = r"C:\Temp\perceptual_dupes"
REVIEW_FOLDER = r"C:\Projects\Duped\final_review"


def perceptual_hash(filepath):
    try:
        img = Image.open(filepath)
        return imagehash.phash(img, hash_size=HASH_SIZE)
    except:
        return None


def main():
    if not os.path.exists(REPORT_FILE):
        print("[ERROR] Cannot find " + REPORT_FILE)
        sys.exit(1)

    with open(REPORT_FILE) as f:
        groups = json.load(f)

    # Create review folder
    os.makedirs(REVIEW_FOLDER, exist_ok=True)

    total_dupes = sum(len(g["duplicates"]) for g in groups)
    print("")
    print("Final Sort")
    print("  Groups: " + str(len(groups)))
    print("  Total dupes to check: " + str(total_dupes))
    print("  Review folder: " + REVIEW_FOLDER)
    print("")

    identical_count = 0
    review_count = 0
    deleted_count = 0
    copied_count = 0
    skipped_count = 0
    errors = 0
    checked = 0

    for gi, group in enumerate(groups):
        keep_path = group["keep"]

        if not os.path.isfile(keep_path):
            skipped_count += len(group["duplicates"])
            continue

        keep_hash = perceptual_hash(keep_path)
        if keep_hash is None:
            skipped_count += len(group["duplicates"])
            continue

        for dupe_path in group["duplicates"]:
            checked += 1
            if checked % 200 == 0:
                print("\r  Processing: " + str(checked) + "/" + str(total_dupes) +
                      " | Deleted: " + str(deleted_count) +
                      " | To review: " + str(copied_count), end="", flush=True)

            # Find the actual file in the dupes folder
            fname = os.path.basename(dupe_path)
            actual_path = os.path.join(DUPES_FOLDER, fname)

            if not os.path.isfile(actual_path):
                # Maybe it has a numbered suffix from the move
                # Try the original path too
                if os.path.isfile(dupe_path):
                    actual_path = dupe_path
                else:
                    skipped_count += 1
                    continue

            dupe_hash = perceptual_hash(actual_path)
            if dupe_hash is None:
                skipped_count += 1
                continue

            distance = keep_hash - dupe_hash

            if distance == 0:
                # Confirmed identical - delete
                identical_count += 1
                try:
                    os.remove(actual_path)
                    deleted_count += 1
                except Exception as e:
                    errors += 1
            else:
                # Distance 1-5, copy to review folder
                review_count += 1
                dest = os.path.join(REVIEW_FOLDER, fname)
                if os.path.exists(dest):
                    stem, ext = os.path.splitext(fname)
                    dest = os.path.join(REVIEW_FOLDER, stem + "_" + str(copied_count) + ext)
                try:
                    shutil.copy2(actual_path, dest)
                    os.remove(actual_path)
                    copied_count += 1
                except Exception as e:
                    errors += 1

    print("\r  Processing: " + str(checked) + "/" + str(total_dupes) + "                              ")
    print("")
    print("  Results:")
    print("  " + "-" * 40)
    print("    Identical (deleted):      " + str(deleted_count))
    print("    Close matches (to review): " + str(copied_count))
    print("    Skipped:                  " + str(skipped_count))
    print("    Errors:                   " + str(errors))
    print("")
    print("  Review the " + str(copied_count) + " files in:")
    print("    " + REVIEW_FOLDER)
    print("")
    print("Done!")


if __name__ == "__main__":
    main()

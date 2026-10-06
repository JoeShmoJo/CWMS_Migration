# -*- coding: utf-8 -*-
"""
Catalog a ResSim simulation.dss into a CSV, one row per time series.

Records that differ only in their D part (the date block) are merged into one
row, so a 30-year run gives one row per series instead of thirty.

Runs on a DESKTOP Python 3 with pydsstools (the hydro39 conda environment),
not inside ResSim. Paste the path to simulation.dss into DSS_PATH below, then:
    conda activate hydro39
    python data/scripts/_migration/catalog_dss.py

A path given on the command line overrides DSS_PATH:
    python data/scripts/_migration/catalog_dss.py "C:/path/to/simulation.dss"

Writes <name>_catalog.csv next to the DSS file, with columns:
    A, B, C, E, F        the pathname parts, D left out
    n_blocks             how many date blocks the series has
    first_D, last_D      first and last D part, sorted as text, not by date
    example_path         one full pathname, for copying into a read
"""

import csv
import os
import sys
from collections import OrderedDict

from pydsstools.heclib.dss import HecDss

################################################################################
# USER INPUT

# Paste the full path to simulation.dss between the quotes. Keep the r in front:
# it stops Python reading the backslashes in a Windows path as escape codes.
DSS_PATH = r""

################################################################################


def catalogSeries(pathnames):
    """
    Group full pathnames by every part except D.
    Returns {(A, B, C, E, F): {"blocks": [D, ...], "example": pathname}},
    in the order the series were first seen.
    """
    series = OrderedDict()
    for pathname in pathnames:
        parts = pathname.split("/")      # ['', A, B, C, D, E, F, '']
        if len(parts) != 8:
            print("Skipping a pathname that is not /A/B/C/D/E/F/: %s" % pathname)
            continue
        a, b, c, d, e, f = parts[1:7]
        key = (a, b, c, e, f)
        if key not in series:
            series[key] = {"blocks": [], "example": pathname}
        series[key]["blocks"].append(d)
    return series


def writeCatalog(series, outPath):
    with open(outPath, "w", newline="", encoding="utf-8") as fh:
        writer = csv.writer(fh)
        writer.writerow(["A", "B", "C", "E", "F", "n_blocks",
                         "first_D", "last_D", "example_path"])
        for (a, b, c, e, f), info in series.items():
            blocks = sorted(info["blocks"])
            writer.writerow([a, b, c, e, f, len(blocks),
                             blocks[0], blocks[-1], info["example"]])


def main():
    dssPath = DSS_PATH
    # Jupyter and VS Code's interactive window pass their own "--f=kernel.json"
    # argument, so only a bare argument counts as a path
    args = [a for a in sys.argv[1:] if not a.startswith("-")]
    if args:
        dssPath = args[0]
    dssPath = dssPath.strip().strip('"')
    if not dssPath:
        sys.exit("No DSS file given. Paste the path to simulation.dss into "
                 "DSS_PATH at the top of catalog_dss.py, or pass it on the "
                 "command line.")
    if not os.path.isfile(dssPath):
        sys.exit("DSS file not found: %s\nCheck the path. It should end in "
                 "simulation.dss, inside the rss\\<simulation> folder."
                 % dssPath)

    fid = HecDss.Open(dssPath)
    try:
        pathnames = fid.getPathnameList("/*/*/*/*/*/*/", sort=1)
    finally:
        fid.close()

    series = catalogSeries(pathnames)
    outPath = os.path.splitext(dssPath)[0] + "_catalog.csv"
    writeCatalog(series, outPath)
    print("%d pathnames -> %d series -> %s" % (len(pathnames), len(series), outPath))


if __name__ == "__main__":
    main()

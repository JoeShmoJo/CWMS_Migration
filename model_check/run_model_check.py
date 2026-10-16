# -*- coding: utf-8 -*-
"""
Run the model check steps chosen in model_check_config.txt, for the
simulation DSS file and alternative named there.

Runs on a DESKTOP Python 3 (the hydro39 conda environment):
    conda activate hydro39
    python model_check\\run_model_check.py

Or open it in Jupyter or VS Code and run it. A different config file can be
given on the command line.
"""

import glob
import os
import re
import sys

HERE = os.path.dirname(os.path.abspath(globals().get("__file__") or os.path.join(os.getcwd(), "x")))
sys.path.insert(0, HERE)

CONFIG_FILE = os.path.join(HERE, "model_check_config.txt")


def readConfig(path):
    """key: value lines, # comments, quotes optional."""
    if not os.path.isfile(path):
        sys.exit("Config file not found: %s" % path)
    values = {}
    for line in open(path, encoding="utf-8-sig"):
        line = line.strip()
        if not line or line.startswith("#") or ":" not in line:
            continue
        key, value = line.split(":", 1)
        values[key.strip()] = value.strip().strip('"').strip("'")
    return values


def isTrue(value):
    return str(value).strip().lower() in ("true", "yes", "1", "y")


def latestRun(simulation, alternative):
    """The newest extract of this simulation and alternative in output/."""
    runs = [d for d in glob.glob(os.path.join(HERE, "output", "%s_%s_*" % (simulation, alternative)))
            if os.path.isfile(os.path.join(d, "run_info.json"))]
    if not runs:
        sys.exit("No extract of %s / %s in %s. Set run_extract: true."
                 % (simulation, alternative, os.path.join(HERE, "output")))
    return max(runs, key=os.path.getmtime)


def main(configFile=None):
    args = [a for a in sys.argv[1:] if not a.startswith("-")]
    config = readConfig(configFile or (args[0] if args else CONFIG_FILE))
    # simulation_dss is the DSS file itself, wherever it is; simulation_folder
    # (the folder holding simulation.dss) still works for older config files
    dssPath = config.get("simulation_dss", "")
    if not dssPath and config.get("simulation_folder"):
        dssPath = os.path.join(config["simulation_folder"], "simulation.dss")
    alternative = config.get("alternative", "")
    # The simulation is named after the folder the DSS file sits in
    parts = re.split(r"[\\/]", dssPath.rstrip("\\/"))
    simulation = parts[-2] if len(parts) > 1 else os.path.splitext(parts[-1])[0]
    steps = [s for s in ("catalog", "extract", "check") if isTrue(config.get("run_" + s))]
    if not steps:
        sys.exit("Nothing to run: set run_catalog, run_extract or run_check to true.")
    if ("catalog" in steps or "extract" in steps) and not os.path.isfile(dssPath):
        sys.exit("DSS file not found: %s\nCheck simulation_dss in the config file." % dssPath)
    if not alternative and ("extract" in steps or "check" in steps):
        sys.exit("Set alternative in %s." % CONFIG_FILE)
    print("Simulation %s, alternative %s: %s" % (simulation, alternative, ", ".join(steps)))

    runDir = None
    if "catalog" in steps:
        print("\n### Catalog")
        import catalog_dss
        catalog_dss.main(dssPath)
    if "extract" in steps:
        print("\n### Extract")
        import extract_dss
        runDir = extract_dss.main(dssPath, alternative)
    if "check" in steps:
        print("\n### Check")
        import check_model
        check_model.main(runDir or latestRun(simulation, alternative),
                         config.get("start_date") or None, config.get("end_date") or None,
                         headroom=isTrue(config.get("run_headroom")))


if __name__ == "__main__":
    main()

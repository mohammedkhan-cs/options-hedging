"""Rerun the options-hedging project from the cached chain snapshot, stopping at the first problem.

    python3 run_all.py            # tests, chain and smile, parity robustness, hedging simulation, then checks
    python3 run_all.py --verbose  # print every stage's output

It NEVER downloads: the Yahoo option chain was pulled once and is cached unedited in data/raw/chain_*. A fresh
pull would be a different day's market. Output of every stage goes to outputs/run_all.log. At the end it compares
key results with the values recorded in ASSUMPTIONS.md."""
import argparse
import hashlib
import subprocess
import sys
import time
from pathlib import Path

import pandas as pd

ROOT = Path(__file__).resolve().parent
PY = sys.executable
LOG = ROOT / "outputs" / "run_all.log"

PRERUN_PREDICTIONS_SHA256 = "3253562cd9d32a898edfd451a9dbcecace11170857a1ee37c858ab790ddc4b1e"   # printed at the chain pull and the simulation
DECISIONS_SHA256 = "44a0c68d8f5d01b62621f556cacbbf662d59799110b80abe6baf0cafb152429c"            # printed at the chain pull

REQUIRED = ["data/raw/chain_calls.csv", "data/raw/chain_puts.csv", "data/raw/chain_meta.json",
            "DECISIONS.md", "PREDICTIONS.md"]
STAGES = [
    ("tests", [PY, "-m", "pytest", "-q"], None),
    ("chain, implied vols, smile (cached snapshot)", [PY, "-m", "src.smile"], "Wrote data/processed/chain_clean_iv.csv"),
    ("parity-window robustness", [PY, "-m", "scripts.check_parity_window"], "Parity window robustness"),
    ("hedging simulation", [PY, "-m", "src.hedging"], "Wrote outputs/tables/hedging_results.csv"),
]

# (name, expected, tolerance). Chain values are exact (deterministic from the cache); simulation values are the printed 2-decimal figures.
EXPECTED = [
    ("forward", 7823.093173457309, 1e-6), ("discount factor", 0.9935841727764925, 1e-9),
    ("ATM implied vol", 0.12788545018834727, 1e-9), ("skew, points", 8.054663764314885, 1e-6),
    ("usable strikes", 390, 0),
    ("mean P&L %, 1.2x, 294 rehedges", -19.90, 0.006), ("mean P&L %, 0.8x, 294 rehedges", 20.03, 0.006),
    ("mean P&L %, 1.0x, 294 rehedges", 0.07, 0.006),
    ("std %, 1.0x, 42 rehedges", 13.46, 0.006), ("std %, 1.0x, 294 rehedges", 5.06, 0.006),
    ("mean P&L %, 1.0x, 294 rehedges, 1bp", -3.04, 0.006), ("avg cost %, 1.0x, 294 rehedges, 1bp", 3.11, 0.006),
]


def sha256(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def run_stage(label, cmd, must_contain=None, verbose=False, cwd=ROOT):
    t0 = time.time()
    p = subprocess.run(cmd, cwd=cwd, capture_output=True, text=True)
    out = (p.stdout or "") + (p.stderr or "")
    ok = p.returncode == 0 and (must_contain is None or must_contain in out)
    print(f"[{'ok' if ok else 'FAILED':6s}] {label} ({time.time() - t0:.1f}s)")
    if verbose or not ok:
        print(out if verbose else "\n".join(out.splitlines()[-25:]))
        if not ok and must_contain and p.returncode == 0:
            print(f"   (exit code 0, but the output did not contain: {must_contain!r})")
    return ok, out


def actual_values(root=ROOT):
    t = root / "outputs" / "tables"
    s = pd.read_csv(t / "chain_summary.csv").iloc[0]
    h = pd.read_csv(t / "hedging_results.csv")

    def pick(col, ratio, n, cost):
        r = h[(h.ratio == ratio) & (h.n_rehedges == n) & (h.cost_bps == cost)]
        assert len(r) == 1, (ratio, n, cost)
        return float(r[col].iloc[0])

    return {
        "forward": float(s["forward"]), "discount factor": float(s["discount_factor"]),
        "ATM implied vol": float(s["atm_iv"]), "skew, points": float(s["skew_points"]),
        "usable strikes": int(s["n_usable_strikes"]),
        "mean P&L %, 1.2x, 294 rehedges": pick("mean_pct", 1.2, 294, 0),
        "mean P&L %, 0.8x, 294 rehedges": pick("mean_pct", 0.8, 294, 0),
        "mean P&L %, 1.0x, 294 rehedges": pick("mean_pct", 1.0, 294, 0),
        "std %, 1.0x, 42 rehedges": pick("std_pct", 1.0, 42, 0), "std %, 1.0x, 294 rehedges": pick("std_pct", 1.0, 294, 0),
        "mean P&L %, 1.0x, 294 rehedges, 1bp": pick("mean_pct", 1.0, 294, 1),
        "avg cost %, 1.0x, 294 rehedges, 1bp": pick("avg_cost_pct", 1.0, 294, 1),
    }


def check_reproducibility(actual, expected=EXPECTED):
    return [(n, actual[n], e, tol) for n, e, tol in expected if abs(actual[n] - e) > tol]


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--verbose", action="store_true")
    args = ap.parse_args()
    missing = [f for f in REQUIRED if not (ROOT / f).exists()]
    if missing:
        sys.exit("STOP: required files are missing (run_all never downloads):\n  " + "\n  ".join(missing))

    pre = ROOT / "PREDICTIONS_prerun.md"
    if pre.exists():
        if sha256(pre) != PRERUN_PREDICTIONS_SHA256:
            sys.exit("STOP: PREDICTIONS_prerun.md does not match the hash printed when the chain was pulled.")
        print("[ok    ] PREDICTIONS_prerun.md matches the hash printed when the chain was pulled")
    else:
        print("[warn  ] PREDICTIONS_prerun.md not preserved; the pre-run hash is logged in ASSUMPTIONS.md only")
    if sha256(ROOT / "DECISIONS.md") != DECISIONS_SHA256:
        print("[warn  ] DECISIONS.md differs from the version hashed at the chain pull; check its change log")

    LOG.parent.mkdir(parents=True, exist_ok=True)
    with open(LOG, "w", encoding="utf-8") as log:
        for label, cmd, must in STAGES:
            ok, out = run_stage(label, cmd, must, args.verbose)
            log.write(f"===== {label} =====\n{out}\n")
            if not ok:
                sys.exit(f"STOP at stage '{label}'. Full output so far is in {LOG.relative_to(ROOT)}.")

    off = check_reproducibility(actual_values())
    if off:
        print("\nREPRODUCIBILITY CHECK FAILED. These results differ from the values recorded in ASSUMPTIONS.md:")
        for n, a, e, tol in off:
            print(f"  {n}: now {a:.6f}, recorded {e:.6f} (tolerance {tol})")
        sys.exit(1)
    print(f"\nAll {len(EXPECTED)} recorded results reproduced. Log: outputs/run_all.log")


if __name__ == "__main__":
    main()
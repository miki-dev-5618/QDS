"""
One-command reproduction of every experiment number and figure.

    python run_experiments.py --seed 2026              # full run (tens of minutes)
    python run_experiments.py --quick                  # smoke test: tiny trial counts, every step
    python run_experiments.py --seed 2026 --resume     # skip steps already completed with the same settings

Each step is one script under experiments/, run in a subprocess with the same
seed. Outputs go to experiments/results/<step>/ together with run.log. Then:

  experiments/results/manifest.json   git commit, Python/package versions, OS/CPU,
                                      seed, trials, quick flag, per-step status and timings
  experiments/results/PPT_NUMBERS.md  every headline number with the file it came from

Steps whose script does not exist yet (or whose dependency is not merged) are
reported as "unavailable" instead of failing the run. To register a new
experiment, add one Step to STEPS (script accepting --seed and --out, plus an
optional headline extractor for PPT_NUMBERS.md).
"""
import argparse
import csv
import hashlib
import json
import os
import platform
import subprocess
import sys
import time
from dataclasses import dataclass, field
from importlib import metadata
from typing import Callable, List, Optional, Tuple

ROOT = os.path.dirname(os.path.abspath(__file__))
EXP = os.path.join(ROOT, "experiments")
RESULTS = os.path.join(EXP, "results")
PACKAGES = ("numpy", "qiskit", "qiskit-aer", "matplotlib", "cryptography", "fastapi", "dilithium-py", "pytest")

Headline = Tuple[str, str, str]  # (claim, value, file relative to repo root)


@dataclass
class Step:
    name: str
    task: str                       # tracker id, e.g. "D6"
    title: str
    script: str                     # path relative to the repo root
    args: Callable[[argparse.Namespace, str], List[str]] = lambda a, out: []
    quick_args: Callable[[str], List[str]] = lambda out: []
    headlines: Optional[Callable[[str], List[Headline]]] = None
    hardware: bool = False
    available: Callable[[], Tuple[bool, str]] = field(default=lambda: (True, ""))


# ---------------------------------------------------------------- helpers
def _rel(path: str) -> str:
    """Repo-relative path for files inside the repo, absolute otherwise."""
    path = os.path.abspath(path)
    try:
        if os.path.commonpath([path, ROOT]) != ROOT:
            return path
        return os.path.relpath(path, ROOT).replace(os.sep, "/")
    except ValueError:
        # On Windows, ValueError: Paths don't have the same drive
        return path


def _trials(a, default_flag="--trials"):
    return [default_flag, str(a.trials)] if a.trials else []


def _harness_raw(out):
    """raw.jsonl written by the harness step, a sibling of this step's output dir."""
    return os.path.join(os.path.dirname(out), "harness", "raw.jsonl")


def _read_csv(path):
    with open(path, newline="", encoding="utf-8") as f:
        return list(csv.DictReader(f))


# ------------------------------------------------------- headline extractors
def trials_headlines(out: str) -> List[Headline]:
    path = os.path.join(out, "results.json")
    with open(path, encoding="utf-8") as f:
        data = json.load(f)
    src, hl = _rel(path), []
    for r in data["rows"]:
        L, s = r["n_bits"], r["scenario"]
        if s == "authentic":
            hl.append((f"Honest false rejection, L={L}", r["flagged_as_threat"], src))
            hl.append((f"Honest single-run false quarantine, L={L}", r["response_quarantine"], src))
        elif s in ("eve_forgery", "eve_intercept", "repudiation", "dishonest_bob"):
            hl.append((f"{s} flagged, L={L}", r["flagged_as_threat"], src))
            hl.append((f"{s} correct class, L={L}", r["correct_class"], src))
        if s == "eve_intercept":
            saved = r["mean_tokens_saved_when_aborted"]
            hl.append((f"eve_intercept early abort (tokens saved), L={L}",
                       f"{r['early_abort']} ({saved:.0%})" if saved else r["early_abort"], src))
    for r in data["lockout"]:
        hl.append((f"Honest sequences ever quarantined ({r['runs_per_trial']} tx), L={r['n_bits']}",
                   r["sequences_ever_quarantined"], src))
    return hl


def tiers_headlines(out: str) -> List[Headline]:
    path = os.path.join(out, "sweep_tiers.json")
    with open(path, encoding="utf-8") as f:
        rows = json.load(f)["rows"]
    src = _rel(path)
    return [(f"Tier 2 wrong attribution, {r['condition']}, L={r['L']} (V2.1 -> V2.2)",
             f"{r['v21_wrong_attribution']} -> {r['v22_wrong_attribution']}", src) for r in rows]


def escalation_headlines(out: str) -> List[Headline]:
    path = os.path.join(out, "ablate_escalation.csv")
    src, hl = _rel(path), []
    for r in _read_csv(path):
        if r["experiment"] == "honest":
            hl.append((f"False quarantine over {r['runs']}x{r['length']} honest tx, {r['rule']}, L={r['L']}",
                       f"{float(r['rate']):.3f} [{float(r['rate_lo']):.3f}, {float(r['rate_hi']):.3f}]", src))
        else:
            hl.append((f"Transmissions to quarantine, {r['condition']}, {r['rule']}, L={r['L']}",
                       f"median {r['median_tx']} [{r['median_lo']}, {r['median_hi']}], mean {r['mean_tx']} "
                       f"[{r['mean_lo']}, {r['mean_hi']}], censored {r['censored']}/{r['runs']}", src))
    return hl


def baselines_headlines(out: str) -> List[Headline]:
    path = os.path.join(out, "baselines.csv")
    src = _rel(path)
    return [(f"{r['metric']} ({r['scenario']}), {r['system']}, L={r['L']}",
             f"{r['value']} [{r['lo']}, {r['hi']}]", src) for r in _read_csv(path)]


def collective_headlines(out: str) -> List[Headline]:
    path = os.path.join(out, "sweep_collective.csv")
    src = _rel(path)
    return [(f"Collective probe theta={float(r['theta']):.4f}, L={r['L']}: detection | mismatch | Eve accuracy",
             f"{float(r['detection_rate']):.3f} [{float(r['detection_lo']):.3f}, {float(r['detection_hi']):.3f}] | "
             f"{float(r['mismatch_rate']):.4f} | {float(r['eve_accuracy']):.4f}", src) for r in _read_csv(path)]


def tightness_headlines(out: str) -> List[Headline]:
    path = os.path.join(out, "tightness.csv")
    src = _rel(path)
    return [(f"Verifier mismatch rate, {r['family']} {r['label']}",
             f"{float(r['rate']):.4f} [{float(r['lo']):.4f}, {float(r['hi']):.4f}]", src) for r in _read_csv(path)]


def adaptive_headlines(out: str) -> List[Headline]:
    path = os.path.join(out, "ablate_adaptive.csv")
    src = _rel(path)
    return [(f"rejected, {r['scenario']}, {r['mode']} allocation, L={r['L']}",
             f"{float(r['rejected']):.3f} [{float(r['rejected_lo']):.3f}, {float(r['rejected_hi']):.3f}], "
             f"tokens {r['mean_tokens']}", src) for r in _read_csv(path)]


def _c2_merged() -> Tuple[bool, str]:
    sys.path.insert(0, ROOT)
    from src.quantum_engine.security import SecurityParameters
    ok = "allocation_policy" in SecurityParameters.__dataclass_fields__
    return ok, "" if ok else "depends on C2 (adaptive allocation), not merged yet"


# ------------------------------------------------------------------ registry
STEPS: List[Step] = [
    Step("harness", "D1", "Seeded experiment harness", "experiments/harness.py",
         args=lambda a, out: ["--seed", str(a.seed), "--out", out] + _trials(a),
         quick_args=lambda out: ["--trials", "5"]),
    Step("trials", "-", "Detection/attribution/response trials (README 13.2)", "experiments/run_trials.py",
         args=lambda a, out: ["--seed", str(a.seed), "--out", out] + _trials(a),
         quick_args=lambda out: ["--trials", "5", "--bits", "16", "--lockout-trials", "3", "--lockout-runs", "3"],
         headlines=trials_headlines),
    Step("sweep_tiers", "-", "One-tier vs two-tier attribution", "experiments/sweep_tiers.py",
         args=lambda a, out: ["--seed", str(a.seed), "--out", out] + _trials(a),
         quick_args=lambda out: ["--trials", "5", "--bits", "16"], headlines=tiers_headlines),
    Step("basis_schedule", "-", "Basis schedule evaluation", "experiments/basis_schedule.py",
         args=lambda a, out: ["--seed", str(a.seed), "--out", out] + _trials(a),
         quick_args=lambda out: ["--trials", "5"]),
    Step("sweep_damping", "A2", "Amplitude/phase damping sweep", "experiments/sweep_damping.py",
         args=lambda a, out: ["--seed", str(a.seed), "--out", os.path.join(out, "sweep_damping.csv")] + _trials(a),
         quick_args=lambda out: ["--trials", "3"]),
    Step("sweep_readout", "A3", "Readout error sweep", "experiments/sweep_readout.py",
         args=lambda a, out: ["--seed", str(a.seed), "--out", os.path.join(out, "sweep_readout.csv")] + _trials(a),
         quick_args=lambda out: ["--trials", "3"]),
    Step("roc", "D2", "ROC curves (from the harness raw.jsonl)", "experiments/make_roc.py",
         args=lambda a, out: ["--seed", str(a.seed), "--out", out, "--raw", _harness_raw(out)],
         quick_args=lambda out: ["--bootstrap", "50"]),
    Step("ablate_early_abort", "D3", "Sequential early abort on vs off", "experiments/ablate_early_abort.py",
         args=lambda a, out: ["--seed", str(a.seed), "--out", out] + _trials(a),
         quick_args=lambda out: ["--trials", "5", "--bits", "16"]),
    Step("ablate_tiers", "D4", "Tier 1 only vs Tier 1 + Tier 2 attribution", "experiments/ablate_tiers.py",
         args=lambda a, out: ["--seed", str(a.seed), "--out", out] + _trials(a),
         quick_args=lambda out: ["--trials", "5", "--bits", "16"]),
    Step("sweep_partial_ir", "B2", "Partial intercept-resend sweep", "experiments/sweep_partial_ir.py",
         args=lambda a, out: ["--seed", str(a.seed), "--out", out] + _trials(a),
         quick_args=lambda out: ["--trials", "3", "--bits", "16", "--fractions", "0.2", "1.0"]),
    Step("sweep_collective", "B3", "One collective (ancilla-probe) attack", "experiments/sweep_collective.py",
         args=lambda a, out: ["--seed", str(a.seed), "--out", out] + _trials(a),
         quick_args=lambda out: ["--trials", "3", "--bits", "16", "--thetas", "0", "1.5708"],
         headlines=collective_headlines),
    Step("ablate_adaptive", "D5", "Fixed vs adaptive allocation", "experiments/ablate_adaptive.py",
         args=lambda a, out: ["--seed", str(a.seed), "--out", out] + _trials(a),
         quick_args=lambda out: ["--trials", "3", "--bits", "16"],
         headlines=adaptive_headlines, available=_c2_merged),
    Step("ablate_escalation", "D6", "Fisher escalation vs k-alert counter", "experiments/ablate_escalation.py",
         args=lambda a, out: ["--seed", str(a.seed), "--out", out] + _trials(a),
         quick_args=lambda out: ["--bits", "16", "--runs", "4", "--transmissions", "40", "--attack-runs", "4",
                                 "--cap", "40"],
         headlines=escalation_headlines),
    Step("baselines", "D7", "Baselines: QBER cutoff / no breaker / full HEDWIG", "experiments/baselines.py",
         args=lambda a, out: ["--seed", str(a.seed), "--out", out] + _trials(a),
         quick_args=lambda out: ["--bits", "16", "--trials", "5", "--seq-runs", "2", "--seq-length", "10"],
         headlines=baselines_headlines),
    Step("tightness", "B4", "Tight-threshold plot", "experiments/plot_tightness.py",
         args=lambda a, out: ["--seed", str(a.seed), "--out", out] + _trials(a),
         quick_args=lambda out: ["--trials", "3"], headlines=tightness_headlines),
    Step("threshold_table", "-", "Threshold table", "experiments/threshold_table.py",
         args=lambda a, out: ["--seed", str(a.seed), "--out", out],
         quick_args=lambda out: []),
    Step("hardware", "-", "IBM hardware / fake-backend runs", "experiments/hardware.py",
         args=lambda a, out: ["--seed", str(a.seed), "--out", out] + _trials(a),
         quick_args=lambda out: ["--trials", "2"], hardware=True),
]


# ------------------------------------------------------------- run machinery
def file_sha256(path: str) -> str:
    with open(path, "rb") as f:
        return hashlib.sha256(f.read()).hexdigest()


def git_info() -> dict:
    def git(*cmd):
        try:
            return subprocess.run(["git", *cmd], cwd=ROOT, capture_output=True, text=True, check=True).stdout.strip()
        except (OSError, subprocess.CalledProcessError):
            return None
    status = git("status", "--porcelain")
    return {"commit": git("rev-parse", "HEAD"), "branch": git("rev-parse", "--abbrev-ref", "HEAD"),
            "dirty": bool(status) if status is not None else None}


def package_versions() -> dict:
    out = {}
    for p in PACKAGES:
        try:
            out[p] = metadata.version(p)
        except metadata.PackageNotFoundError:
            out[p] = None
    return out


def machine_info() -> dict:
    cpu = platform.processor() or platform.machine()
    if sys.platform == "darwin":
        try:
            cpu = subprocess.run(["sysctl", "-n", "machdep.cpu.brand_string"], capture_output=True, text=True,
                                 check=True).stdout.strip() or cpu
        except (OSError, subprocess.CalledProcessError):
            pass
    return {"os": platform.platform(), "machine": platform.machine(), "cpu": cpu, "cpu_count": os.cpu_count(),
            "python": sys.version.split()[0], "python_implementation": platform.python_implementation()}


def step_config(step: Step, argv: List[str], args: argparse.Namespace) -> dict:
    return {"argv": argv, "seed": args.seed, "trials": args.trials, "quick": args.quick,
            "script_sha256": file_sha256(os.path.join(ROOT, step.script))}


def run_step(step: Step, args: argparse.Namespace, root: str) -> dict:
    out = os.path.join(root, step.name)
    rec = {"name": step.name, "task": step.task, "title": step.title, "script": step.script, "out": _rel(out)}
    if step.hardware and args.skip_hardware:
        return {**rec, "status": "skipped", "reason": "--skip-hardware"}
    if not os.path.exists(os.path.join(ROOT, step.script)):
        return {**rec, "status": "unavailable", "reason": f"{step.script} does not exist yet"}
    ok, why = step.available()
    if not ok:
        return {**rec, "status": "unavailable", "reason": why}

    argv = step.args(args, out) + (step.quick_args(out) if args.quick else [])  # argparse: last flag wins
    cfg = step_config(step, argv, args)
    marker = os.path.join(out, ".done.json")
    if args.resume and os.path.exists(marker):
        with open(marker, encoding="utf-8") as f:
            done = json.load(f)
        if done.get("config") == cfg:
            return {**rec, "status": "cached", "argv": argv, "seconds": done.get("seconds"),
                    "finished": done.get("finished")}

    os.makedirs(out, exist_ok=True)
    print(f"[{step.name}] {step.script} {' '.join(argv)}", flush=True)
    t0 = time.time()
    with open(os.path.join(out, "run.log"), "w", encoding="utf-8") as log:
        proc = subprocess.run([sys.executable, os.path.join(ROOT, step.script), *argv], cwd=ROOT,
                              stdout=log, stderr=subprocess.STDOUT)
    seconds = round(time.time() - t0, 2)
    status = "ok" if proc.returncode == 0 else "failed"
    print(f"[{step.name}] {status} in {seconds:.1f} s", flush=True)
    rec.update(status=status, argv=argv, seconds=seconds, returncode=proc.returncode,
               finished=time.strftime("%Y-%m-%d %H:%M:%S"))
    if status == "ok":
        with open(marker, "w", encoding="utf-8") as f:
            json.dump({"config": cfg, "seconds": seconds, "finished": rec["finished"]}, f, indent=2)
    elif os.path.exists(marker):
        os.remove(marker)
    return rec


def collect_headlines(step: Step, rec: dict) -> List[Headline]:
    if rec["status"] not in ("ok", "cached"):
        return []
    out = os.path.join(ROOT, rec["out"])
    if not step.headlines:
        return []
    try:
        return step.headlines(out)
    except Exception as exc:  # a missing output file must not hide the rest of the report
        return [(f"(could not extract headlines: {type(exc).__name__}: {exc})", "-", rec["out"])]


def write_ppt_numbers(path: str, manifest: dict, numbers: dict):
    g = manifest["git"]
    lines = [
        "# PPT numbers", "",
        "Auto-generated by `run_experiments.py`; do not edit by hand. Every value below comes from the file in "
        "its *source* column. Rates are fractions with 95% Wilson intervals unless stated otherwise.", "",
        f"- Command: `{manifest['command']}`",
        f"- Seed {manifest['seed']}, trials {manifest['trials'] or 'script defaults'}"
        f"{' (QUICK MODE: smoke-test sizes, not for the PPT)' if manifest['quick'] else ''}",
        f"- Commit `{g['commit']}` on `{g['branch']}`{' (uncommitted changes present)' if g['dirty'] else ''}",
        f"- Generated {manifest['finished']}", "",
    ]
    for rec in manifest["steps"]:
        head = f"## {rec['title']} ({rec['task']}, `{rec['name']}`)" if rec["task"] != "-" else \
               f"## {rec['title']} (`{rec['name']}`)"
        lines += [head, ""]
        if rec["status"] not in ("ok", "cached"):
            lines += [f"*{rec['status']}*: {rec.get('reason') or 'see ' + rec['out'] + '/run.log'}", ""]
            continue
        hl = numbers.get(rec["name"], [])
        if not hl:
            files = sorted(f for f in os.listdir(os.path.join(ROOT, rec["out"])) if not f.startswith(".")
                           and f != "run.log")
            lines += ["No headline extractor; outputs: " + ", ".join(f"`{rec['out']}/{f}`" for f in files), ""]
            continue
        lines += ["| claim | value | source |", "|---|---|---|"]
        lines += [f"| {c} | {v} | `{s}` |" for c, v, s in hl]
        lines.append("")
    with open(path, "w", encoding="utf-8") as f:
        f.write("\n".join(lines) + "\n")


def main(argv=None) -> dict:
    ap = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    ap.add_argument("--seed", type=int, default=2026)
    ap.add_argument("--trials", type=int, default=None, help="override every step's trial count (default: each "
                                                              "script's own default)")
    ap.add_argument("--quick", action="store_true", help="smoke test: tiny trial counts for every step")
    ap.add_argument("--skip-hardware", action="store_true", help="skip steps that need IBM hardware/fake backends")
    ap.add_argument("--resume", action="store_true", help="skip steps already completed with identical settings")
    ap.add_argument("--out", default=RESULTS, help=argparse.SUPPRESS)
    args = ap.parse_args(argv)

    os.makedirs(args.out, exist_ok=True)
    started = time.strftime("%Y-%m-%d %H:%M:%S")
    t0 = time.time()
    records, numbers = [], {}
    for step in STEPS:
        rec = run_step(step, args, args.out)
        records.append(rec)
        hl = collect_headlines(step, rec)
        if hl:
            numbers[step.name] = hl
        if rec["status"] in ("unavailable", "skipped"):
            print(f"[{step.name}] {rec['status']}: {rec['reason']}", flush=True)

    manifest = {
        "command": "python run_experiments.py " + " ".join(argv if argv is not None else sys.argv[1:]),
        "seed": args.seed, "trials": args.trials, "quick": args.quick, "skip_hardware": args.skip_hardware,
        "resume": args.resume, "started": started, "finished": time.strftime("%Y-%m-%d %H:%M:%S"),
        "seconds": round(time.time() - t0, 2), "git": git_info(), "packages": package_versions(),
        "machine": machine_info(), "steps": records,
    }
    with open(os.path.join(args.out, "manifest.json"), "w", encoding="utf-8") as f:
        json.dump(manifest, f, indent=2)
    write_ppt_numbers(os.path.join(args.out, "PPT_NUMBERS.md"), manifest, numbers)
    failed = [r["name"] for r in records if r["status"] == "failed"]
    print(f"\nWrote {_rel(os.path.join(args.out, 'manifest.json'))} and "
          f"{_rel(os.path.join(args.out, 'PPT_NUMBERS.md'))}"
          + (f"\nFAILED steps: {', '.join(failed)} (see their run.log)" if failed else ""))
    return manifest


if __name__ == "__main__":
    sys.exit(1 if any(r["status"] == "failed" for r in main()["steps"]) else 0)

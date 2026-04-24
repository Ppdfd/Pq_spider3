"""
run_all_tests.py — AUDIT FIX NOTES
===================================================================
CHANGES vs original:
  [HONESTY] _avg now returns None for empty lists (not 0.0), so
            "no data" is visually distinguishable from "very fast".
  [FAIRNESS] The end-to-end total row now shows TWO figures:
             - Core total (Phases 1+2+5+6) — apples-to-apples
               across all schemes.
             - Ours-full total (1+2+3+4+5+6) — includes PQ-SPIDER's
               gateway and scheduler phases, which refs do not have.
             The old code lumped everything into one total and
             silently charged Ours for phases 3 and 4 while refs
             got 0, making Ours look worse in end-to-end comparisons
             without disclosing the asymmetry.
"""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))

from phase1_initialization import main as phase1_main
from phase2_iiot_encrypt   import main as phase2_main
from phase3_edge_gateway   import main as phase3_main
from phase4_load_balance   import main as phase4_main
from phase5_fog_node       import main as phase5_main
from phase6_user_decrypt   import main as phase6_main

from utils.dataset_loader import DataLoader
from utils.resource_profiler import profile_phase, format_resource_table


SCHEMES = [
    ("Ours",            "ours_metrics.json"),
    ("Ref[4] Poomekum", "ref4_metrics.json"),
    ("Ref[35] Zaheer",  "ref35_metrics.json"),
    ("Ref[36] Man",     "ref36_metrics.json"),
]

# Tagged which phases are cross-scheme comparable.
PHASES = [
    ("Phase 1 (Init)",      "phase1_initialization", "total_init",
     True),
    ("Phase 2 (Dev Enc)",   "phase2_iiot_encrypt",   "total_device_latency",
     True),
    ("Phase 3 (Gateway)*",  "phase3_edge_gateway",   "total_gateway_latency",
     False),
    ("Phase 4 (Spider++)*", "phase4_load_balance",   "total_scheduler_latency",
     False),
    ("Phase 5 (Fog)",       "phase5_fog_node",       "total_fog_latency",
     True),
    ("Phase 6 (User Dec)",  "phase6_user_decrypt",   "total_user_latency",
     True),
]


def _avg(v):
    # AUDIT FIX: None for empty list so we can distinguish from 0.
    if isinstance(v, list):
        return (sum(v) / len(v)) if v else None
    return v


def _fmt(val):
    return f"{val:>14.2f}" if isinstance(val, (int, float)) else f"{'--':>14}"


def grand_summary():
    loader = DataLoader()
    root = Path(__file__).parent

    data = {}
    for phase_label, subdir, metric_key, _ in PHASES:
        phase_dir = root / subdir
        data[phase_label] = {}
        for scheme_label, fname in SCHEMES:
            m = loader.load_metrics(phase_dir, fname)
            data[phase_label][scheme_label] = (
                _avg(m.get(metric_key)) if m else None)

    print("\n" + "=" * 92)
    print("  PQ-SPIDER FULL EVALUATION — Grand Summary  (all values in ms)")
    print("  * = phase only meaningful for Ours (refs have no analogue)")
    print("=" * 92)
    header = f"{'Phase':<24}" + "".join(f"{s:>14}" for s, _ in SCHEMES)
    print(header)
    print("-" * 92)

    for phase_label, _, _, _ in PHASES:
        row = f"{phase_label:<24}"
        for scheme_label, _ in SCHEMES:
            v = data[phase_label][scheme_label]
            row += _fmt(v)
        print(row)
    print("-" * 92)

    # Core total (Phases 1, 2, 5, 6 — all schemes have these).
    print(f"{'Core total (1+2+5+6)':<24}", end="")
    for scheme_label, _ in SCHEMES:
        total = 0.0
        missing = False
        for phase_label, _, _, comparable in PHASES:
            if not comparable:
                continue
            v = data[phase_label][scheme_label]
            if v is None:
                missing = True
                break
            total += v
        print(_fmt(total if not missing else None), end="")
    print()

    # Ours-full total (all 6 phases — only meaningful for Ours).
    print(f"{'Ours-full (1+2+3+4+5+6)':<24}", end="")
    for scheme_label, _ in SCHEMES:
        if scheme_label != "Ours":
            print(_fmt(None), end="")
            continue
        total = 0.0
        missing = False
        for phase_label, _, _, _ in PHASES:
            v = data[phase_label][scheme_label]
            if v is None:
                missing = True
                break
            total += v
        print(_fmt(total if not missing else None), end="")
    print()
    print("=" * 92)
    print()


def main():
    print("\n" + "#" * 70)
    print("#  PQ-SPIDER  FULL 6-PHASE EVALUATION  (Ours vs [4], [35], [36])    #")
    print("#" * 70)

    import io, contextlib

    # Import all individual scheme runners
    from phase1_initialization.ours import run_phase1_simulation
    from phase1_initialization.ref_4 import run_phase1_ref4
    from phase1_initialization.ref_35 import run_phase1_ref35
    from phase1_initialization.ref_36 import run_phase1_ref36

    from phase2_iiot_encrypt.ours import run_phase2_simulation
    from phase2_iiot_encrypt.ref_4 import run_phase2_ref4
    from phase2_iiot_encrypt.ref_35 import run_phase2_ref35
    from phase2_iiot_encrypt.ref_36 import run_phase2_ref36

    from phase3_edge_gateway.ours import run_phase3_simulation

    from phase4_load_balance.ours import run_phase4_simulation
    from phase4_load_balance.ref_22 import run_phase4_ref22
    from phase4_load_balance.ref_37 import run_phase4_ref37
    from phase4_load_balance.ref_39 import run_phase4_ref39

    from phase5_fog_node.ours import run_phase5_simulation
    from phase5_fog_node.ref_4 import run_phase5_ref4
    from phase5_fog_node.ref_35 import run_phase5_ref35
    from phase5_fog_node.ref_36 import run_phase5_ref36

    from phase6_user_decrypt.ours import run_phase6_simulation
    from phase6_user_decrypt.ref_4 import run_phase6_ref4
    from phase6_user_decrypt.ref_35 import run_phase6_ref35
    from phase6_user_decrypt.ref_36 import run_phase6_ref36

    # Per-scheme resource profiling: {phase: {scheme: metrics}}
    phase_resources = {
        "Phase 1": {}, "Phase 2": {}, "Phase 3": {},
        "Phase 4": {}, "Phase 5": {}, "Phase 6": {},
    }

    # ═══════════════════════════════════════════════════════════
    # Run Ours: full chain Phase 1→2→3→4→5→6
    # ═══════════════════════════════════════════════════════════
    print("\n" + "=" * 70)
    print("  SCHEME: Ours (PQ-SPIDER)")
    print("=" * 70)

    _, rm = profile_phase(run_phase1_simulation)
    phase_resources["Phase 1"]["Ours"] = rm

    _, rm = profile_phase(run_phase2_simulation)
    phase_resources["Phase 2"]["Ours"] = rm

    _, rm = profile_phase(run_phase3_simulation)
    phase_resources["Phase 3"]["Ours"] = rm

    _, rm = profile_phase(run_phase4_simulation)
    phase_resources["Phase 4"]["Ours"] = rm

    _, rm = profile_phase(run_phase5_simulation)
    phase_resources["Phase 5"]["Ours"] = rm

    _, rm = profile_phase(run_phase6_simulation)
    phase_resources["Phase 6"]["Ours"] = rm

    # ═══════════════════════════════════════════════════════════
    # Run Ref[4] Poomekum: Phase 1→2→5→6
    # ═══════════════════════════════════════════════════════════
    print("\n" + "=" * 70)
    print("  SCHEME: Ref[4] Poomekum et al.")
    print("=" * 70)

    _, rm = profile_phase(run_phase1_ref4)
    phase_resources["Phase 1"]["Ref[4]"] = rm

    _, rm = profile_phase(run_phase2_ref4)
    phase_resources["Phase 2"]["Ref[4]"] = rm

    _, rm = profile_phase(run_phase5_ref4)
    phase_resources["Phase 5"]["Ref[4]"] = rm

    _, rm = profile_phase(run_phase6_ref4)
    phase_resources["Phase 6"]["Ref[4]"] = rm

    # ═══════════════════════════════════════════════════════════
    # Run Ref[35] Zaheer: Phase 1→2→5→6
    # ═══════════════════════════════════════════════════════════
    print("\n" + "=" * 70)
    print("  SCHEME: Ref[35] Zaheer et al.")
    print("=" * 70)

    _, rm = profile_phase(run_phase1_ref35)
    phase_resources["Phase 1"]["Ref[35]"] = rm

    _, rm = profile_phase(run_phase2_ref35)
    phase_resources["Phase 2"]["Ref[35]"] = rm

    _, rm = profile_phase(run_phase5_ref35)
    phase_resources["Phase 5"]["Ref[35]"] = rm

    _, rm = profile_phase(run_phase6_ref35)
    phase_resources["Phase 6"]["Ref[35]"] = rm

    # ═══════════════════════════════════════════════════════════
    # Run Ref[36] Man: Phase 1→2→5→6
    # ═══════════════════════════════════════════════════════════
    print("\n" + "=" * 70)
    print("  SCHEME: Ref[36] Man et al.")
    print("=" * 70)

    _, rm = profile_phase(run_phase1_ref36)
    phase_resources["Phase 1"]["Ref[36]"] = rm

    _, rm = profile_phase(run_phase2_ref36)
    phase_resources["Phase 2"]["Ref[36]"] = rm

    _, rm = profile_phase(run_phase5_ref36)
    phase_resources["Phase 5"]["Ref[36]"] = rm

    _, rm = profile_phase(run_phase6_ref36)
    phase_resources["Phase 6"]["Ref[36]"] = rm

    # ═══════════════════════════════════════════════════════════
    # Phase 4 baselines (use Ours' data, just different schedulers)
    # ═══════════════════════════════════════════════════════════
    print("\n" + "=" * 70)
    print("  PHASE 4 BASELINES")
    print("=" * 70)

    # Re-run Ours phases 1-3 to ensure consistent state for schedulers
    with contextlib.redirect_stdout(io.StringIO()):
        run_phase1_simulation()
        run_phase2_simulation()
        run_phase3_simulation()

    for label, func in [("Ref[22]", run_phase4_ref22),
                         ("Ref[37]", run_phase4_ref37),
                         ("Ref[39]", run_phase4_ref39)]:
        _, rm = profile_phase(func)
        phase_resources["Phase 4"][label] = rm

    # ═══════════════════════════════════════════════════════════
    # Generate graphs (not profiled)
    # ═══════════════════════════════════════════════════════════
    import config
    if config.GENERATE_GRAPHS:
        print("\n" + "#" * 70)
        print("# GENERATING GRAPHS")
        print("#" * 70 + "\n")

        # Generate the complete paper-style Spider++ evaluation graph set:
        # Graph 1, 2, 3, 4, 5, 6, and 8. Graph 7 is intentionally skipped.
        if getattr(config, "GENERATE_SPIDERPP_FULL_EVALUATION", True):
            try:
                from evaluation.spiderpp_full_evaluation import run_all_graphs as run_spiderpp_full_graphs
                run_spiderpp_full_graphs()
            except Exception as exc:
                print(f"[WARN] Spider++ full evaluation graph generation failed: {exc}")

    # ═══════════════════════════════════════════════════════════
    # Summaries
    # ═══════════════════════════════════════════════════════════
    grand_summary()
    print(format_resource_table_detailed(phase_resources))
    print()


def format_resource_table_detailed(phase_resources):
    """Format per-scheme per-phase resource metrics as an IEEE table."""
    lines = []
    lines.append("")
    lines.append("=" * 100)
    lines.append("  RESOURCE USAGE — Real CPU & Memory per Scheme (measured via psutil)")
    lines.append("=" * 100)
    lines.append(f"{'Phase':<12} {'Scheme':<12} {'CPU Time':>10} {'Wall Time':>10} "
                 f"{'Peak RSS':>10} {'Mem Delta':>10}")
    lines.append(f"{'':12} {'':12} {'(ms)':>10} {'(ms)':>10} "
                 f"{'(MB)':>10} {'(MB)':>10}")
    lines.append("-" * 100)

    for phase_label, schemes in phase_resources.items():
        for scheme_label, rm in schemes.items():
            lines.append(
                f"{phase_label:<12} {scheme_label:<12} "
                f"{rm['cpu_time_ms']:10.2f} {rm['wall_time_ms']:10.2f} "
                f"{rm['peak_memory_mb']:10.1f} {rm['memory_delta_mb']:10.1f}"
            )
        lines.append("-" * 100)

    lines.append("=" * 100)
    return "\n".join(lines)


if __name__ == "__main__":
    main()


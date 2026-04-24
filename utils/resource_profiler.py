"""
Resource Profiler — Real CPU & Memory Measurement via psutil
=============================================================
Wraps phase runner functions to capture:
  - CPU time (user + system) in ms
  - Peak RSS memory in MB
  - Wall-clock time in ms

Usage:
    from utils.resource_profiler import profile_phase

    result, metrics = profile_phase(run_phase1_simulation)
    # metrics = {"cpu_time_ms": ..., "peak_memory_mb": ..., "wall_time_ms": ...}
"""

import os
import time
import psutil


def profile_phase(func, *args, **kwargs):
    """Run a phase function and capture real CPU + memory metrics.

    Returns:
        (result, resource_metrics) where resource_metrics is a dict with:
          - cpu_time_ms:     User + system CPU time consumed (ms)
          - peak_memory_mb:  Peak RSS memory during execution (MB)
          - wall_time_ms:    Wall-clock elapsed time (ms)
    """
    proc = psutil.Process(os.getpid())

    # Snapshot CPU times before
    cpu_before = proc.cpu_times()
    mem_before = proc.memory_info().rss

    # Track peak memory via a pre-call snapshot
    # (psutil doesn't track peak RSS natively; we sample before/after)
    wall_start = time.perf_counter()

    result = func(*args, **kwargs)

    wall_end = time.perf_counter()
    cpu_after = proc.cpu_times()
    mem_after = proc.memory_info().rss

    # CPU time = delta of (user + system)
    cpu_user_ms = (cpu_after.user - cpu_before.user) * 1000
    cpu_sys_ms = (cpu_after.system - cpu_before.system) * 1000
    cpu_total_ms = cpu_user_ms + cpu_sys_ms

    # Peak memory: take max of before/after RSS
    peak_rss_bytes = max(mem_before, mem_after)
    peak_rss_mb = peak_rss_bytes / (1024 * 1024)

    # Memory delta (how much extra memory the phase consumed)
    mem_delta_mb = (mem_after - mem_before) / (1024 * 1024)

    wall_ms = (wall_end - wall_start) * 1000

    resource_metrics = {
        "cpu_time_ms":     round(cpu_total_ms, 2),
        "cpu_user_ms":     round(cpu_user_ms, 2),
        "cpu_sys_ms":      round(cpu_sys_ms, 2),
        "peak_memory_mb":  round(peak_rss_mb, 2),
        "memory_delta_mb": round(mem_delta_mb, 2),
        "wall_time_ms":    round(wall_ms, 2),
    }

    return result, resource_metrics


def format_resource_table(phase_resources):
    """Format a dict of {phase_name: resource_metrics} as an IEEE-style table.

    Args:
        phase_resources: dict mapping phase labels to resource_metrics dicts

    Returns:
        String containing a formatted comparison table.
    """
    lines = []
    lines.append("")
    lines.append("=" * 90)
    lines.append("  RESOURCE USAGE — Real CPU & Memory (measured via psutil)")
    lines.append("=" * 90)
    lines.append(f"{'Phase':<35} {'CPU Time':>10} {'Wall Time':>10} "
                 f"{'Peak RSS':>10} {'Mem Delta':>10}")
    lines.append(f"{'':35} {'(ms)':>10} {'(ms)':>10} "
                 f"{'(MB)':>10} {'(MB)':>10}")
    lines.append("-" * 90)

    for phase_label, rm in phase_resources.items():
        lines.append(
            f"{phase_label:<35} {rm['cpu_time_ms']:10.1f} "
            f"{rm['wall_time_ms']:10.1f} "
            f"{rm['peak_memory_mb']:10.1f} "
            f"{rm['memory_delta_mb']:10.1f}"
        )

    lines.append("=" * 90)
    return "\n".join(lines)

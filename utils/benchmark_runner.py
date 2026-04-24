"""
Benchmark Runner & IEEE Plot Helpers
=====================================
Shared utilities for multi-round benchmarking and publication-quality graph
generation.  Used by each phase's main.py to generate scalability charts.

Eliminates the duplicated warm-up / test-round / redirect_stdout / try-finally
pattern that was previously copy-pasted across 7 separate graph scripts.
"""

import io
import contextlib
import matplotlib
matplotlib.use('Agg')  # Non-interactive backend for PDF generation
import matplotlib.pyplot as plt


# ─────────────────────────────────────────────────────────────
# Benchmark Loop
# ─────────────────────────────────────────────────────────────
def run_benchmark(func, rounds, warmup, extract_metric, setup_fn=None):
    """
    Run *func* (warmup + rounds) times with stdout suppressed.

    Parameters
    ----------
    func : callable
        The simulation function to benchmark. Must return a metrics dict.
    rounds : int
        Number of measured rounds (after warmup).
    warmup : int
        Number of discarded warm-up rounds.
    extract_metric : callable
        Given a metrics dict, return the numeric value to average.
    setup_fn : callable or None
        Optional setup function to run once before the benchmark loop.

    Returns
    -------
    float
        The average metric value across the measured rounds.
    """
    if setup_fn is not None:
        with contextlib.redirect_stdout(io.StringIO()):
            setup_fn()

    times = []
    for r in range(warmup + rounds):
        with contextlib.redirect_stdout(io.StringIO()):
            metrics = func()
        if r >= warmup:
            times.append(extract_metric(metrics))
    return sum(times) / len(times) if times else 0.0


def run_benchmark_chain(chain, rounds, warmup, extract_metric):
    """
    Run a chain of functions as setup (all but last), then benchmark the last.

    Parameters
    ----------
    chain : list of callables
        All functions except the last are run as setup (once).
        The last function is benchmarked for `warmup + rounds` iterations.
    rounds : int
        Number of measured rounds.
    warmup : int
        Number of discarded warm-up rounds.
    extract_metric : callable
        Given a metrics dict from the last function, return the value to average.

    Returns
    -------
    float
        The average metric value.
    """
    if len(chain) > 1:
        with contextlib.redirect_stdout(io.StringIO()):
            for fn in chain[:-1]:
                fn()

    target = chain[-1]
    times = []
    for r in range(warmup + rounds):
        with contextlib.redirect_stdout(io.StringIO()):
            metrics = target()
        if r >= warmup:
            times.append(extract_metric(metrics))
    return sum(times) / len(times) if times else 0.0


# ─────────────────────────────────────────────────────────────
# IEEE-Style Plot Helpers
# ─────────────────────────────────────────────────────────────

MARKERS = ['o', 's', '^', 'D', 'v', 'p']
LINESTYLES = ['-', '--', '-.', ':', '-', '--']
COLORS = ['#1f77b4', '#2ca02c', '#d62728', '#9467bd', '#ff7f0e', '#8c564b']


def plot_ieee_line(x_values, data_dict, xlabel, ylabel, title, output_path,
                   caption=None):
    """
    Generate an IEEE-style line chart with multiple series.

    Parameters
    ----------
    x_values : list
        X-axis tick values.
    data_dict : dict
        {series_name: [y_values]} for each line to plot.
    xlabel, ylabel, title : str
        Axis labels and chart title.
    output_path : Path
        Where to save the PDF.
    caption : str or None
        Optional figtext footnote (used for audit fairness disclosures).
    """
    plt.figure(figsize=(8, 6))

    for i, (name, y_values) in enumerate(data_dict.items()):
        plt.plot(x_values, y_values,
                 marker=MARKERS[i % len(MARKERS)],
                 linestyle=LINESTYLES[i % len(LINESTYLES)],
                 color=COLORS[i % len(COLORS)],
                 label=name, markersize=8, linewidth=2)

    plt.xlabel(xlabel, fontsize=14, fontweight='bold')
    plt.ylabel(ylabel, fontsize=14, fontweight='bold')
    plt.title(title, fontsize=16, fontweight='bold')
    plt.grid(True, linestyle='--', alpha=0.7)
    plt.legend(fontsize=12, loc='upper left')
    plt.xticks(x_values, fontsize=12)
    plt.yticks(fontsize=12)

    if caption:
        plt.figtext(0.5, 0.01, caption,
                     ha='center', fontsize=9, style='italic', wrap=True)
        plt.tight_layout(rect=[0, 0.08, 1, 1])
    else:
        plt.tight_layout()

    output_path.parent.mkdir(parents=True, exist_ok=True)
    plt.savefig(output_path, format='pdf', dpi=300)
    plt.close()
    print(f"  -> Graph saved: {output_path}")


def plot_ieee_bar(names, values, ylabel, title, output_path,
                  value_fmt=".2f", value_suffix=" ms"):
    """
    Generate an IEEE-style bar chart.

    Parameters
    ----------
    names : list of str
        Bar labels (x-axis).
    values : list of float
        Bar heights.
    ylabel, title : str
        Axis label and chart title.
    output_path : Path
        Where to save the PDF.
    """
    plt.figure(figsize=(8, 6))

    colors = COLORS[:len(names)]
    bars = plt.bar(names, values, color=colors, width=0.6, alpha=0.85,
                   edgecolor='black', linewidth=0.8)

    for bar in bars:
        yval = bar.get_height()
        label = f"{yval:{value_fmt}}{value_suffix}"
        plt.text(bar.get_x() + bar.get_width() / 2, yval + 0.05,
                 label, ha='center', va='bottom',
                 fontsize=12, fontweight='bold')

    plt.ylabel(ylabel, fontsize=14, fontweight='bold')
    plt.title(title, fontsize=16, fontweight='bold')
    plt.grid(True, axis='y', linestyle='--', alpha=0.7)
    plt.xticks(fontsize=12, fontweight='bold')
    plt.yticks(fontsize=12)

    max_val = max(values) if values else 1
    plt.ylim(0, max_val + (max_val * 0.15))
    plt.tight_layout()

    output_path.parent.mkdir(parents=True, exist_ok=True)
    plt.savefig(output_path, format='pdf', dpi=300)
    plt.close()
    print(f"  -> Graph saved: {output_path}")

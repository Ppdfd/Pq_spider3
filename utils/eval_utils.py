#!/usr/bin/env python3
"""
Spider Evaluation Utilities
==================================

Shared utilities for the PQ-SPIDER evaluation framework: seeding,
plotting (IEEE-style), CSV export, and common data helpers.

Used by all graph modules in ``graphs/`` and by ``run_all_graphs.py``.

Generated graphs (via graph modules):
  Graph 1  CP-ABE Setup Latency vs Attributes
  Graph 2  Cache / Reuse-Aware Scheduling
  Graph 3  CP-ABE Encryption Cost at Fog
  Graph 4  CP-ABE Decryption Cost at User
  Graph 5  Homogeneous Fog Nodes (Load Balancing)
  Graph 6  Heterogeneous Fog Nodes (Load Balancing)
  Graph 7  Recovery Time vs Failure Rate
  Graph 8  Intra-node Enclave Scheduling
  Graph 9  Routing Intelligence (Task Distribution)

Outputs:
    graphs/spider_full_evaluation/*.png
    graphs/spider_full_evaluation/raw/*.csv
"""

from __future__ import annotations

import csv
import hashlib as _hashlib
import json
import math
import os
import random
import sys as _sys
import tempfile
import time as _time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Dict, Iterable, List, Tuple

# Use a non-interactive backend and writable config directory so the script
# runs cleanly on servers, CI runners, Docker containers, and student laptops.
os.environ.setdefault("MPLBACKEND", "Agg")
os.environ.setdefault("MPLCONFIGDIR", str(Path(tempfile.gettempdir()) / "spider_mpl_cache"))

import matplotlib.pyplot as plt
import numpy as np


# ---------------------------------------------------------------------------
# Global configuration
# ---------------------------------------------------------------------------

GLOBAL_SEED = 20260424


def project_root() -> Path:
    """
    Resolve the project root whether this file is executed from:
      - Pq_spider_new-main/evaluation/spider_full_evaluation.py, or
      - copied directly into the project root.
    """

    here = Path(__file__).resolve()
    if here.parent.name in ("evaluation", "utils"):
        return here.parents[1]
    return here.parent


ROOT_DIR = project_root()
OUT_DIR = ROOT_DIR / "graphs" / "spider_full_evaluation"
RAW_DIR = OUT_DIR / "raw"

# Ensure project root is on sys.path for crypto_primitives imports
if str(ROOT_DIR) not in _sys.path:
    _sys.path.insert(0, str(ROOT_DIR))


@dataclass
class PlotConfig:
    """Centralized IEEE-style plot configuration."""

    dpi: int = 350
    figsize: Tuple[float, float] = (6.8, 4.4)
    linewidth: float = 2.15
    markersize: float = 5.8
    band_alpha: float = 0.13
    font_size: int = 10
    title_size: int = 11
    label_size: int = 10
    legend_size: int = 8


PLOT = PlotConfig()
MARKERS = ["o", "s", "^", "D", "v", "P", "X"]

SCHEME_STYLES = {
    "Spider (Ours)": {"color": "#1A73E8", "marker": "o"},
    "Spider Reuse-Aware Cache (Ours)": {"color": "#1A73E8", "marker": "o"},
    "Spider Secure Task Delegation (Ours)": {"color": "#1A73E8", "marker": "o"},
    "Ref[4]": {"color": "#E8710A", "marker": "s"},
    "Ref[22]": {"color": "#E8710A", "marker": "s"},
    "Ref[37]": {"color": "#34A853", "marker": "^"},
    "Ref[39]": {"color": "#EA4335", "marker": "D"},
    "No Cache-Aware Scheduling": {"color": "#E8710A", "marker": "v"},
    "Random Cache Placement": {"color": "#34A853", "marker": "s"},
    "No Delegation": {"color": "#E8710A", "marker": "x"},
    "Simple Retry / Reassignment": {"color": "#34A853", "marker": "v"},
    "Round-Robin": {"color": "#E8710A", "marker": "s"},
    "Least-Queue": {"color": "#34A853", "marker": "^"},
}


def set_global_seed(seed: int = GLOBAL_SEED) -> np.random.Generator:
    """Seed Python and NumPy RNGs for reproducible simulations."""

    random.seed(seed)
    np.random.seed(seed)
    return np.random.default_rng(seed)


def ensure_dirs() -> None:
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    RAW_DIR.mkdir(parents=True, exist_ok=True)


def configure_matplotlib() -> None:
    """Consistent clean plot style suitable for IEEE papers."""

    plt.rcParams.update(
        {
            "font.family": "serif",
            "font.size": PLOT.font_size,
            "axes.titlesize": PLOT.title_size,
            "axes.labelsize": PLOT.label_size,
            "legend.fontsize": PLOT.legend_size,
            "axes.grid": True,
            "grid.alpha": 0.28,
            "grid.linestyle": "--",
            "lines.linewidth": PLOT.linewidth,
            "lines.markersize": PLOT.markersize,
            "figure.dpi": PLOT.dpi,
            "savefig.dpi": PLOT.dpi,
            "savefig.bbox": "tight",
            "axes.spines.top": False,
            "axes.spines.right": False,
            "pdf.fonttype": 42,
            "ps.fonttype": 42,
        }
    )


def ar1_noise(n: int, rng: np.random.Generator, scale: float = 0.03, rho: float = 0.45) -> np.ndarray:
    """Correlated noise; avoids perfect straight lines without making curves random."""

    eps = rng.normal(0.0, scale, size=n)
    out = np.zeros(n)
    for i in range(n):
        out[i] = eps[i] if i == 0 else rho * out[i - 1] + eps[i]
    return out


def noisy_curve(
    base: np.ndarray,
    rng: np.random.Generator,
    pct: float = 0.035,
    rho: float = 0.35,
    monotonic: str | None = None,
) -> np.ndarray:
    """Apply correlated multiplicative noise and optional trend stabilization."""

    values = np.asarray(base, dtype=float) * (1.0 + ar1_noise(len(base), rng, pct, rho))
    values = np.maximum(values, 0.01)

    if monotonic == "increasing":
        values = np.maximum.accumulate(values)
    elif monotonic == "decreasing":
        # Enforce broad decreasing trend while preserving small gaps.
        values = values[::-1]
        values = np.maximum.accumulate(values)
        values = values[::-1]

    return values


def summarize_runs(values: List[np.ndarray]) -> Tuple[np.ndarray, np.ndarray]:
    arr = np.vstack(values)
    # Use median to be robust against OS-level scheduling spikes and outliers
    return np.median(arr, axis=0), arr.std(axis=0)


def save_csv(path: Path, x_name: str, x_values: Iterable[float], series: Dict[str, np.ndarray]) -> None:
    """Save raw data behind each graph to make the plots reproducible."""

    labels = list(series.keys())
    with path.open("w", newline="") as f:
        writer = csv.writer(f)
        writer.writerow([x_name] + labels)
        for i, x in enumerate(x_values):
            writer.writerow([x] + [float(series[label][i]) for label in labels])


def plot_lines(
    x: np.ndarray,
    series: Dict[str, Tuple[np.ndarray, np.ndarray | None]],
    title: str,
    xlabel: str,
    ylabel: str,
    filename: str,
    ylim_bottom: float | None = 0.0,
) -> None:
    """Plot lines with optional standard-deviation bands and save PNG/PDF."""

    fig, ax = plt.subplots(figsize=PLOT.figsize)
    for idx, (label, (mean, std)) in enumerate(series.items()):
        style = SCHEME_STYLES.get(label, {"color": None, "marker": MARKERS[idx % len(MARKERS)]})
        marker = style["marker"]
        color = style["color"]
        line = ax.plot(x, mean, marker=marker, color=color, label=label)[0]
        # Confidence bands removed intentionally as requested by the user

    ax.set_title(title)
    ax.set_xlabel(xlabel)
    ax.set_ylabel(ylabel)
    if ylim_bottom is not None:
        ax.set_ylim(bottom=ylim_bottom)
    ax.legend(frameon=True, loc="best")
    fig.tight_layout()
    fig.savefig(OUT_DIR / f"{filename}.png")
    plt.close(fig)


def _load_json(path: Path) -> dict:
    """Load a JSON metrics file."""
    with open(path) as f:
        return json.load(f)


def _avg(v) -> float:
    """Return average of a list or the scalar itself."""
    if isinstance(v, list):
        return float(np.mean(v)) if v else 0.0
    return float(v)


def _res(phase: str, filename: str) -> Path:
    """Resolve a results JSON file path."""
    return ROOT_DIR / phase / "results" / filename


def plot_bar(
    labels: List[str],
    values: List[float],
    title: str,
    ylabel: str,
    filename: str,
) -> None:
    """Simple bar chart saved as PNG."""
    fig, ax = plt.subplots(figsize=PLOT.figsize)
    x = np.arange(len(labels))
    colors = [SCHEME_STYLES.get(l, {}).get("color", "#888888") for l in labels]
    bars = ax.bar(x, values, color=colors, width=0.55)
    ax.set_xticks(x)
    ax.set_xticklabels(labels, fontsize=PLOT.font_size)
    ax.set_ylabel(ylabel)
    ax.set_title(title)
    ax.set_ylim(bottom=0)
    for bar, val in zip(bars, values):
        ax.text(bar.get_x() + bar.get_width() / 2, bar.get_height() + max(values) * 0.015,
                f"{val:.2f}", ha="center", va="bottom", fontsize=8)
    fig.tight_layout()
    fig.savefig(OUT_DIR / f"{filename}.png")
    plt.close(fig)


def save_csv_simple(path: Path, header: List[str], rows: List[List]) -> None:
    """Save a simple CSV."""
    with open(path, "w", newline="") as f:
        w = csv.writer(f)
        w.writerow(header)
        for row in rows:
            w.writerow(row)


# ---------------------------------------------------------------------------
# Part A: Encryption evaluation
# ---------------------------------------------------------------------------

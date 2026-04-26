import os
import csv
import hashlib as _hashlib
import json
import math
import random
import sys as _sys
import tempfile
import time as _time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Dict, Iterable, List, Tuple

import numpy as np
import matplotlib.pyplot as plt

from utils.eval_utils import (
    GLOBAL_SEED, PLOT, MARKERS, SCHEME_STYLES, OUT_DIR, RAW_DIR, ROOT_DIR,
    set_global_seed, ensure_dirs, configure_matplotlib, summarize_runs,
    save_csv, plot_lines, plot_bar, save_csv_simple, noisy_curve, ar1_noise
)

def graph1_setup_phase(rng: np.random.Generator, reps: int = 15) -> Dict[str, np.ndarray]:
    """
    Graph 1: CP-ABE Setup Latency vs Number of Attributes.

    Measures the FULL Phase-I CP-ABE setup as defined in each paper:

    Spider++ (PQ_SPIDER, Eq 1-5):
      Eq 1:  ID_j = H(attr_j)                         — attribute hashing
      Eq 2:  (MPK, MSK) ← Setup(1^λ, {ID_j})          — matrix A + dual-Regev keys
             For each attr: t_j ← small_vec, u_j = A^T · t_j   (mat-vec multiply)
      Eq 3-4: (M, ρ) ← PolicyTreeGen(T_ID), cached     — LSSS precomputation
      Eq 5:  SK_u ← KeyGen(MSK, {ID_j})                — user key issuance

    Ref[4] (Poomekum, Algorithm 1):
      1. a ← R_q                                       — uniform public polynomial
      2. s ← D_σ                                       — master secret (Gaussian)
      3. For each attr: GenAttributePair(a, σ)
           ψ ← D_σ, e ← D_σ, B = a·ψ + e              — poly multiply in R_q
      4. salt, attribute index mapping
    """
    from crypto_primitives.cp_abe import LatticeCPABE
    from phase1_initialization.ref_4 import (
        _sample_uniform_poly, _sample_gaussian, gen_attribute_pair,
        N_RING, Q_MOD, SIGMA_GAUSS,
    )

    attrs = np.arange(5, 55, 5)

    ours_runs: List[np.ndarray] = []
    ref4_runs: List[np.ndarray] = []

    for _ in range(reps):
        o_vals = []
        r_vals = []
        for n_attr in attrs:
            n_attr_int = int(n_attr)
            attr_names = [f"Attr{i}" for i in range(n_attr_int)]
            user_attrs = attr_names[: max(1, n_attr_int // 2)]

            # ── Spider++ (Ours): Full Phase I (Eq 1-5) ──
            t0 = _time.perf_counter()
            # Eq 2: Setup — generates n×n matrix A
            aa = LatticeCPABE(n=256, q=3329)
            aa.setup()
            # Eq 1: ID_j = H(attr_j)
            for a_name in attr_names:
                aa.hash_attribute(a_name)
            # Eq 2 cont.: dual-Regev key generation per attribute
            #   _ensure_attr: t_j ← small_vec(n), u_j = A^T · t_j mod q
            _ = aa.keygen({}, attr_names)
            # Eq 3-4: LSSS policy precomputation & cache
            policy = {"type": "AND", "attributes": user_attrs}
            _ = aa.ree_build_policy(policy)
            # Eq 5: User key issuance
            _ = aa.keygen({}, user_attrs)
            o_vals.append((_time.perf_counter() - t0) * 1000)

            # ── Ref[4]: Algorithm 1 — Ring-LWE static setup ──
            t0 = _time.perf_counter()
            # Step 1: a ← R_q, s ← D_σ
            a_poly = _sample_uniform_poly(N_RING, Q_MOD)
            _s_master = _sample_gaussian(N_RING, SIGMA_GAUSS, Q_MOD)
            # Step 2: For each attr → GenAttributePair (Gaussian + poly mul)
            for _ in range(n_attr_int):
                gen_attribute_pair(a_poly, Q_MOD, N_RING, SIGMA_GAUSS)
            # Epoch pair (Algorithm 2 lines 2-4, always generated during setup)
            gen_attribute_pair(a_poly, Q_MOD, N_RING, SIGMA_GAUSS)
            r_vals.append((_time.perf_counter() - t0) * 1000)

        ours_runs.append(np.array(o_vals))
        ref4_runs.append(np.array(r_vals))

    ours_mean, ours_std = summarize_runs(ours_runs)
    ref4_mean, ref4_std = summarize_runs(ref4_runs)

    data = {"Ref[4]": ref4_mean, "Spider++ (Ours)": ours_mean}
    save_csv(RAW_DIR / "graph1_setup_phase.csv", "Number of Attributes", attrs, data)
    plot_lines(
        attrs,
        {"Ref[4]": (ref4_mean, ref4_std),
         "Spider++ (Ours)": (ours_mean, ours_std)},
        "Graph 1: CP-ABE Setup Latency",
        "Number of Attributes",
        "CP-ABE Setup Latency (ms)",
        "graph1_setup_phase",
    )
    return data


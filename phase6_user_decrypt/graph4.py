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

def graph4_cpabe_decryption(rng: np.random.Generator, reps: int = 8) -> Dict[str, np.ndarray]:
    """
    Graph 4: CP-ABE Decryption Cost vs Number of Attributes.

    Both papers perform Lattice CP-ABE decryption at the user.
    The difference is the caching model:

    Ref[4] (Poomekum et al.): No batch awareness.
      - Per PACKET: full policy_eval (LSSS weight computation) + decrypt
      - No caching of LSSS reconstruction weights between packets

    Spider (Ours): Batch-aware with cached policy_eval.
      - First packet: full policy_eval + cpabe_decrypt
      - Subsequent packets in batch: reuse cached LSSS weights
      - Only cpabe_decrypt per additional packet
      → Amortized cost decreases with batch size
    """
    from crypto_primitives.cp_abe import LatticeCPABE

    attrs = np.arange(5, 55, 5)
    N_BATCH = 20

    ours_runs: List[np.ndarray] = []
    ref4_runs: List[np.ndarray] = []

    for _ in range(reps):
        o_vals = []
        r_vals = []
        for n_attr in attrs:
            n_attr_int = int(n_attr)
            universe = [f"Attr{i}" for i in range(n_attr_int)]
            user_attrs = universe
            aa = LatticeCPABE(n=256, q=3329)
            aa.setup()
            for a in universe:
                aa.hash_attribute(a)
            sk_u = aa.keygen({}, user_attrs)
            policy = {"type": "AND", "attributes": user_attrs}

            # Encrypt N_BATCH ciphertexts with the same policy
            policy_pkg = aa.ree_build_policy(policy)
            cts = []
            for _ in range(N_BATCH):
                k_aes = os.urandom(32)
                tee_out = aa.tee_partial_encrypt(k_aes, policy_pkg)
                cts.append(aa.ree_finalize_ct(policy_pkg, tee_out))

            # ── Ref[4]: Full decrypt per packet (no cached policy_eval) ──
            ref4_times = []
            for ct in cts:
                t0 = _time.perf_counter()
                pe = aa.policy_eval(ct, sk_u)
                if pe is not None:
                    aa.cpabe_decrypt(ct, sk_u, pe)
                ref4_times.append((_time.perf_counter() - t0) * 1000)
            r_vals.append(float(np.mean(ref4_times)))

            # ── Ours: Cached policy_eval across batch ──
            # First packet: full policy_eval + cpabe_decrypt
            # Packets 2-N: reuse cached pe, only cpabe_decrypt
            ours_times = []
            cached_pe = None
            for ct in cts:
                t0 = _time.perf_counter()
                if cached_pe is None:
                    cached_pe = aa.policy_eval(ct, sk_u)
                if cached_pe is not None:
                    aa.cpabe_decrypt(ct, sk_u, cached_pe)
                ours_times.append((_time.perf_counter() - t0) * 1000)
            o_vals.append(float(np.mean(ours_times)))

        ours_runs.append(np.array(o_vals))
        ref4_runs.append(np.array(r_vals))

    ours_mean, ours_std = summarize_runs(ours_runs)
    ref4_mean, ref4_std = summarize_runs(ref4_runs)

    data = {"Ref[4]": ref4_mean, "Spider (Ours)": ours_mean}
    save_csv(RAW_DIR / "graph4_cpabe_decryption.csv",
             "Number of Attributes", attrs, data)
    plot_lines(
        attrs,
        {"Ref[4]": (ref4_mean, ref4_std),
         "Spider (Ours)": (ours_mean, ours_std)},
        "Graph 4: CP-ABE Decryption Cost (User)",
        "Number of Attributes",
        "Decryption Latency (ms)",
        "graph4_cpabe_decryption_user",
    )
    return data


# ---------------------------------------------------------------------------
# Part B: Fog load-balancing and recovery evaluation
# ---------------------------------------------------------------------------


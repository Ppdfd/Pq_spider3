"""
Task and Node Generators for PQ-SPIDER Simulation
===================================================

Functions to generate synthetic IIoT workload task streams and
fog node / enclave populations for the discrete-event simulator.
"""

import json
from pathlib import Path
from typing import Dict, List

import numpy as np

import config

from .params import SIMULATION_PARAMS
from .models import WorkloadTask, FogNode, Enclave


# ---------------------------------------------------------------------------
# Phase 5 service-time loader (used by intra-node scheduling)
# ---------------------------------------------------------------------------

_PHASE5_METRICS = Path(__file__).parent.parent / "phase5_fog_node" / "results" / "ours_metrics.json"
_PHASE5_CACHE: Dict[str, float] = {}

def _load_phase5_service_ms() -> float:
    """Load measured per-task service time from Phase 5 fog node metrics (cached)."""
    if "val" in _PHASE5_CACHE:
        return _PHASE5_CACHE["val"]
    if _PHASE5_METRICS.exists():
        with open(_PHASE5_METRICS) as f:
            data = json.load(f)
        val = float(data.get("total_fog_latency", 56.35))
        print(f"  [phase5] Measured fog latency: {val:.2f}ms")
    else:
        val = 56.35
        print("  [phase5] No metrics found, using default 56.35ms")
    _PHASE5_CACHE["val"] = val
    return val


# ---------------------------------------------------------------------------
# Task generation
# ---------------------------------------------------------------------------

def generate_tasks(n_tasks: int, rng: np.random.Generator, offered_load: float = 1.0) -> List[WorkloadTask]:
    """Generate the task stream shared by all algorithms in one experiment."""

    arrivals = np.cumsum(rng.exponential(7.2 / offered_load, size=n_tasks))
    tasks: List[WorkloadTask] = []

    for arrival in arrivals:
        records = int(rng.integers(6, 28))
        attrs = int(rng.integers(8, 48))
        depth = int(rng.integers(2, 7))
        payload = float(rng.lognormal(mean=3.0, sigma=0.45))
        risk = float(np.clip(rng.beta(2.2, 4.0), 0.02, 0.98))
        # IEC 61784-2 Class 2 (soft real-time IIoT): 100-500ms range.
        # We use (150, 400) to challenge schedulers without being trivial.
        deadline = float(rng.uniform(150, 400))

        tee_work = 8.0 + 0.52 * records + 0.30 * attrs + 1.7 * depth + 0.020 * payload
        ree_work = 5.0 + 0.22 * records + 0.24 * attrs + 1.15 * depth + 0.010 * payload
        tee_work *= float(rng.lognormal(0.0, 0.08))
        ree_work *= float(rng.lognormal(0.0, 0.08))

        epc_req = max(8.0, 16.0 + 0.65 * records + 0.42 * attrs + 3.4 * depth + float(rng.normal(0, 2.5)))

        tasks.append(
            WorkloadTask(
                arrival_ms=float(arrival),
                records=records,
                attrs=attrs,
                policy_depth=depth,
                payload_kb=payload,
                risk=risk,
                deadline_ms=deadline,
                tee_work=float(tee_work),
                ree_work=float(ree_work),
                epc_req_mb=float(epc_req),
            )
        )

    return tasks


# ---------------------------------------------------------------------------
# Fog node generation
# ---------------------------------------------------------------------------

def generate_nodes(count: int, heterogeneous: bool, rng: np.random.Generator) -> List[FogNode]:
    """Generate homogeneous or heterogeneous fog-node populations."""

    nodes: List[FogNode] = []
    for node_id in range(count):
        if heterogeneous:
            # AUDIT FIX: Realistic heterogeneity with 2-5× TEE/REE mismatch.
            # Real-world OP-TEE vs native Linux has perhaps 2-5× overhead.
            # Previous code used 50-70× mismatches which are unrealistic.
            node_type = int(rng.integers(0, 4))
            if node_type == 0:
                # Fast balanced node
                tee_rate = float(rng.uniform(2.5, 3.5))
                ree_rate = float(rng.uniform(2.5, 3.5))
            elif node_type == 1:
                # TEE-heavy: faster TEE, slower REE (realistic 2-4× mismatch)
                tee_rate = float(rng.uniform(2.5, 4.0))
                ree_rate = float(rng.uniform(0.8, 1.5))
            elif node_type == 2:
                # REE-heavy: slower TEE, faster REE (realistic 2-4× mismatch)
                tee_rate = float(rng.uniform(0.8, 1.5))
                ree_rate = float(rng.uniform(2.5, 4.0))
            else:
                # Slow node: both sides constrained
                tee_rate = float(rng.uniform(0.6, 1.2))
                ree_rate = float(rng.uniform(0.6, 1.2))

            network = float(rng.uniform(5.5, 32.0))
            epc_total = float(rng.choice([96, 128, 192, 256, 384, 512]) + rng.normal(0, 8.0))
            trust = float(rng.uniform(0.82, 0.995))
            energy_factor = float(rng.uniform(0.70, 1.45))
        else:
            tee_rate = float(rng.normal(1.12, 0.035))
            ree_rate = float(rng.normal(1.12, 0.035))
            network = float(rng.normal(10.0, 0.65))
            epc_total = float(rng.normal(256.0, 6.0))
            trust = float(rng.normal(0.97, 0.008))
            energy_factor = float(rng.normal(1.0, 0.03))

        policy_cached = bool(rng.random() < 0.30)
        kyber_cached = bool(rng.random() < 0.30)

        nodes.append(
            FogNode(
                node_id=node_id,
                tee_rate=max(0.1, tee_rate),
                ree_rate=max(0.1, ree_rate),
                network_ms=max(1.0, network),
                epc_total_mb=max(64.0, epc_total),
                trust=float(np.clip(trust, 0.50, 1.0)),
                energy_factor=max(0.25, energy_factor),
                policy_cached=policy_cached,
                kyber_cached=kyber_cached,
            )
        )
    return nodes


# ---------------------------------------------------------------------------
# Enclave generation (intra-node)
# ---------------------------------------------------------------------------

def generate_enclaves(n_enclaves: int, rng: np.random.Generator) -> List[Enclave]:
    """
    Create a *heterogeneous* enclave pool from real OP-TEE measurements.

    EPC per enclave: from QEMU measured epc_free (TA_DATA_SIZE = 2MB) [A].
    Service rate:    from QEMU measured service_rate (393 ops/s → 0.393) [A].
    Heterogeneity:   rate × cited range from SIMULATION_PARAMS.
    """
    from .optee_bench.loader import load_measurements

    measurements = load_measurements(config)

    raw_rate = float(measurements.get("service_rate", config.MEASURED_SERVICE_RATE))
    base_rate = raw_rate / 1000.0   # ops/sec → normalized rate factor
    base_cont = float(measurements.get("contention", 0.0))

    # Per-enclave EPC from QEMU measured epc_free (default: TA_DATA_SIZE = 2MB)
    measured_epc_per_enclave = float(measurements.get("epc_free", 2_097_152))

    # Rate multipliers: model thermal throttling and core heterogeneity.
    # Range from SIMULATION_PARAMS (cited: ARM thermal docs + Amacher'19).
    rate_lo, rate_hi = SIMULATION_PARAMS["rate_multiplier_range"]
    rate_multipliers = sorted(
        [float(rng.uniform(rate_lo, rate_hi)) for _ in range(n_enclaves)],
        reverse=True,
    )

    # EPC heterogeneity: TA_DATA_SIZE is a compile-time constant [E],
    # so all enclaves on the same node get near-identical allocation.
    # Small jitter (±5%) models OS-level TZDRAM fragmentation.
    epc_lo, epc_hi = SIMULATION_PARAMS["epc_multiplier_range"]
    epc_multipliers = [float(rng.uniform(epc_lo, epc_hi)) for _ in range(n_enclaves)]

    enclaves: List[Enclave] = []
    for i in range(n_enclaves):
        rate = max(0.1, base_rate * rate_multipliers[i])
        epc_total_i = measured_epc_per_enclave * epc_multipliers[i]

        # Heterogeneity: simulate realistic distribution of background TAs.
        # Per Wang & Zhou [6]: production fog enclaves see 35-70% EPC
        # utilization typically. We model 1/3 lightly loaded, 1/3 moderate,
        # 1/3 heavy.
        # AUDIT FIX: Randomized loading from probability distribution using the seed (B5).
        load_choice = float(rng.choice([0.90, 0.65, 0.40]))
        epc_usable = epc_total_i * load_choice
        
        # Add slight jitter for tasks
        prior_tasks = int(rng.integers(0, 6))
        epc_used = prior_tasks * config.PACKET_EPC_BYTES * 8
        epc_avail = max(0.0, epc_usable - epc_used)

        # Generate explicit finish times for prior tasks
        prior_avail = float(prior_tasks * rng.uniform(3.0, 12.0))
        prior_finish_times = []
        if prior_tasks > 0:
            avg_svc = prior_avail / prior_tasks
            for pt in range(prior_tasks):
                prior_finish_times.append(float((pt + 1) * avg_svc))

        enclaves.append(
            Enclave(
                enc_id=i,
                service_rate=rate,
                epc_total=epc_total_i,
                epc_available=epc_avail,
                contention=base_cont + prior_tasks * 0.002,
                queue_length=prior_tasks,
                available_ms=prior_avail,
                recent_count=prior_tasks,
                _finish_times=prior_finish_times,
            )
        )
    return enclaves

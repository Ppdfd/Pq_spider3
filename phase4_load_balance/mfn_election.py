"""
Master Fog Node (MFN) Election for PQ-SPIDER
==============================================

Implements PQ-SPIDER2 paper Section IV (Eq 112-116):
  Eq 112: Score(F_j) = alpha1*C_j + alpha2*M_j - alpha3*N_j + alpha4*R_j + alpha5*T_j
  Eq 113: R_j = 1 - (beta1 * avg_enclave_load + beta2 * rho_epc + beta3 * REE_backlog)
  Eq 114: 0 <= R_j <= 1
  Eq 115: MFN = argmax(Score(F_j) - gamma * DeltaScore(F_j))
  Eq 116: F_j in F_candidate if R_j >= tau_readiness
"""

from typing import List, Optional
from dataclasses import dataclass

import numpy as np

import config


@dataclass
class MFNCandidate:
    """Fog node candidate for MFN election."""
    node_id: int
    capability: float      # C_j — normalized processing capability
    enclave_memory: float  # M_j — available enclave memory
    network_latency: float # N_j — latency to neighbors/gateways
    trust: float           # T_j — execution trustworthiness
    # Enclave-level state for readiness computation
    enclave_queue_ratios: List[float]  # q_{j,k} / Q_max for each enclave
    epc_pressure: float               # rho_epc(F_j)
    ree_backlog_ratio: float           # Q_REE_j / Q_REE_max
    # Previous score for stability penalty
    prev_score: float = 0.0



def compute_readiness(candidate: MFNCandidate) -> float:
    """
    Eq 113: R_j = 1 - (beta1 * avg_enclave_load + beta2 * rho_epc + beta3 * REE_backlog)

    Captures fine-grained enclave imbalance and secure-execution contention.
    """
    if candidate.enclave_queue_ratios:
        avg_enclave_load = sum(candidate.enclave_queue_ratios) / len(candidate.enclave_queue_ratios)
    else:
        avg_enclave_load = 0.0

    R_j = 1.0 - (
        config.MFN_BETA1_ENCLAVE_QUEUE * avg_enclave_load
        + config.MFN_BETA2_EPC_PRESSURE * candidate.epc_pressure
        + config.MFN_BETA3_REE_BACKLOG * candidate.ree_backlog_ratio
    )
    # Eq 114: 0 <= R_j <= 1
    return max(0.0, min(1.0, R_j))


def compute_score(candidate: MFNCandidate) -> float:
    """
    Eq 112: Score(F_j) = alpha1*C_j + alpha2*M_j - alpha3*N_j + alpha4*R_j + alpha5*T_j
    """
    R_j = compute_readiness(candidate)
    return (
        config.ALPHA1_CAPABILITY * candidate.capability
        + config.ALPHA2_MEMORY * candidate.enclave_memory
        - config.ALPHA3_NETWORK * candidate.network_latency
        + config.ALPHA4_READINESS * R_j
        + config.ALPHA5_TRUST * candidate.trust
    )


def elect_mfn(candidates: List[MFNCandidate]) -> Optional[MFNCandidate]:
    """
    Eq 115-116: Stability-aware MFN selection.

    MFN = argmax_{F_j in F_candidate} (Score(F_j) - gamma * DeltaScore(F_j))

    Where F_candidate = {F_j | R_j >= tau_readiness}
    """
    # Eq 116: Filter by readiness threshold
    eligible = [c for c in candidates if compute_readiness(c) >= config.TAU_READINESS]

    if not eligible:
        # Fallback: select from all candidates if none meet threshold
        eligible = candidates

    if not eligible:
        return None

    best_candidate = None
    best_adjusted_score = float("-inf")

    for c in eligible:
        score = compute_score(c)
        # Eq 115: Stability penalty = gamma * |Score(t) - Score(t-1)|
        delta_score = abs(score - c.prev_score)
        adjusted_score = score - config.GAMMA_STABILITY * delta_score

        if adjusted_score > best_adjusted_score:
            best_adjusted_score = adjusted_score
            best_candidate = c

    return best_candidate


def simulate_mfn_election(
    n_nodes: int = 10,
    seed: int = 20260424,
) -> dict:
    """
    Run a simulated MFN election with random fog node states.
    Returns the elected MFN and all scores for evaluation.
    """
    rng = np.random.default_rng(seed)

    candidates = []
    for i in range(n_nodes):
        n_enclaves = int(rng.integers(2, 6))
        c = MFNCandidate(
            node_id=i,
            capability=float(rng.uniform(0.3, 1.0)),
            enclave_memory=float(rng.uniform(0.2, 1.0)),
            network_latency=float(rng.uniform(0.05, 0.4)),
            trust=float(rng.uniform(0.7, 1.0)),
            enclave_queue_ratios=[float(rng.uniform(0.0, 0.8)) for _ in range(n_enclaves)],
            epc_pressure=float(rng.uniform(0.0, 0.6)),
            ree_backlog_ratio=float(rng.uniform(0.0, 0.5)),
            prev_score=float(rng.uniform(0.0, 0.5)),
        )
        candidates.append(c)

    mfn = elect_mfn(candidates)

    return {
        "elected_node_id": mfn.node_id if mfn else None,
        "scores": {c.node_id: compute_score(c) for c in candidates},
        "readiness": {c.node_id: compute_readiness(c) for c in candidates},
        "n_eligible": sum(1 for c in candidates if compute_readiness(c) >= config.TAU_READINESS),
    }

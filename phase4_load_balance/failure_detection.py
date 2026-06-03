"""
Group-Based Failure Detection and Secure Workload Recovery for PQ-SPIDER
=========================================================================

Implements PQ-SPIDER2 paper Section V (Eq 117-125):
  Eq 117-118: Monitoring group partitioning G_i = {F_1,...,F_s}, 3 <= s <= 7
  Eq 119:     Number of groups g = ceil(N / s)
  Eq 120:     Authenticated heartbeat: Heartbeat(F_j, t) = (ID_j, t, epoch_j, status_j, sigma_j)
  Eq 121:     Elapsed heartbeat interval: Delta_t_j = t_current - t_last(F_j)
  Eq 122:     Suspicious if Delta_t_j > tau_h
  Eq 123:     Quorum: q >= ceil(s / 2)
  Eq 124:     Secure delegation capsule: Xi_k = (ID_k, SubID_k, Prog_k, Meta_k, CT_partial_k, T_k, epoch_k, sigma_k)
  Eq 125:     Recovery node: F_recover = argmin SpiderScore(F_j, B_k)
"""

from typing import List, Dict, Optional, Tuple
from dataclasses import dataclass, field
import math
import hashlib

import numpy as np

import config
from .models import FogNode
from .generators import generate_nodes


@dataclass
class FogNodeState:
    """Runtime monitoring state of a fog node for failure detection.

    Composes a :class:`models.FogNode` reference for scheduling data
    (capability, trust, EPC, rates) while tracking monitoring-specific
    state (heartbeat, epoch, failure status) separately.
    """
    fog_node: FogNode
    is_alive: bool = True
    last_heartbeat_ms: float = 0.0
    epoch: int = 0
    status: str = "healthy"
    suspicious_count: int = 0
    declared_failed: bool = False

    @property
    def node_id(self) -> int:
        return self.fog_node.node_id


@dataclass
class MonitoringGroup:
    """Eq 117: G_i = {F_1, F_2, ..., F_s}"""
    group_id: int
    members: List[FogNodeState] = field(default_factory=list)

    @property
    def size(self) -> int:
        return len(self.members)

    @property
    def quorum(self) -> int:
        """Eq 123: q >= ceil(s / 2)"""
        return math.ceil(self.size / 2)


@dataclass
class DelegationCapsule:
    """
    Eq 124: Secure delegation capsule for workload recovery.
    Xi_k = (ID_k, SubID_k, Prog_k, Meta_k, CT_partial_k, T_k, epoch_k, sigma_k)
    """
    workload_id: str
    sub_batch_id: str
    progress: float          # 0.0 to 1.0
    metadata: dict
    partial_ct: bytes
    timestamp_ms: float
    epoch: int
    signature: bytes         # Integrity protection

    @staticmethod
    def create(workload_id: str, sub_batch_id: str, progress: float,
               metadata: dict, partial_ct: bytes, timestamp_ms: float,
               epoch: int, signing_key: bytes) -> "DelegationCapsule":
        """Create an authenticated delegation capsule."""
        # Sign to prevent stale-state replay and unauthorized injection (Eq 124)
        sig_input = (
            workload_id.encode() + sub_batch_id.encode()
            + str(progress).encode() + str(epoch).encode()
            + str(timestamp_ms).encode()
        )
        signature = hashlib.sha256(signing_key + sig_input).digest()
        return DelegationCapsule(
            workload_id=workload_id,
            sub_batch_id=sub_batch_id,
            progress=progress,
            metadata=metadata,
            partial_ct=partial_ct,
            timestamp_ms=timestamp_ms,
            epoch=epoch,
            signature=signature,
        )


def partition_into_groups(
    nodes: List[FogNodeState],
    group_size: int = config.DEFAULT_GROUP_SIZE,
) -> List[MonitoringGroup]:
    """
    Eq 117-119: Partition fog layer into bounded-size monitoring groups.
    g = ceil(N / s) groups, each with 3 <= s <= 7 members.
    """
    s = max(config.GROUP_SIZE_MIN, min(config.GROUP_SIZE_MAX, group_size))
    groups = []
    for i in range(0, len(nodes), s):
        group_members = nodes[i: i + s]
        groups.append(MonitoringGroup(group_id=len(groups), members=group_members))
    return groups


def generate_heartbeat(node: FogNodeState, current_ms: float) -> dict:
    """
    Eq 120: Heartbeat(F_j, t) = (ID_j, t, epoch_j, status_j, sigma_j)
    """
    sig_input = (
        str(node.node_id).encode()
        + str(current_ms).encode()
        + str(node.epoch).encode()
        + node.status.encode()
    )
    sigma = hashlib.sha256(sig_input).digest()
    return {
        "node_id": node.node_id,
        "timestamp": current_ms,
        "epoch": node.epoch,
        "status": node.status,
        "sigma": sigma,
    }


def check_heartbeat_timeout(
    node: FogNodeState,
    current_ms: float,
    tau_h: float = config.HEARTBEAT_TIMEOUT_MS,
) -> bool:
    """
    Eq 121-122: Check if a node's heartbeat has timed out.
    Delta_t_j = t_current - t_last(F_j)
    Suspicious if Delta_t_j > tau_h
    """
    delta_t = current_ms - node.last_heartbeat_ms
    return delta_t > tau_h


def quorum_failure_detection(
    group: MonitoringGroup,
    suspect_node: FogNodeState,
    current_ms: float,
    tau_h: float = config.HEARTBEAT_TIMEOUT_MS,
) -> bool:
    """
    Eq 123: Quorum-based collaborative failure confirmation.
    A node is declared failed only if >= q neighboring peers
    independently observe timeout violations.
    """
    votes = 0
    for member in group.members:
        if member.node_id == suspect_node.node_id:
            continue
        if not member.is_alive or member.declared_failed:
            continue
        # Each live peer checks the suspect's heartbeat independently
        if check_heartbeat_timeout(suspect_node, current_ms, tau_h):
            votes += 1

    return votes >= group.quorum


def detect_failures(
    groups: List[MonitoringGroup],
    current_ms: float,
    tau_h: float = config.HEARTBEAT_TIMEOUT_MS,
) -> List[int]:
    """
    Run failure detection across all monitoring groups.
    Returns list of node IDs declared as failed.
    """
    failed_ids = []
    for group in groups:
        for member in group.members:
            if member.declared_failed or not member.is_alive:
                continue
            # Eq 122: Check if suspicious
            if check_heartbeat_timeout(member, current_ms, tau_h):
                # Eq 123: Quorum confirmation
                if quorum_failure_detection(group, member, current_ms, tau_h):
                    member.declared_failed = True
                    failed_ids.append(member.node_id)
    return failed_ids


def _recovery_spider_score(node: FogNode) -> float:
    """
    Eq 125 / Eq 40: SpiderScore-aligned recovery selection.

    Reuses the same :class:`models.FogNode` data model and the same
    ``config.W*`` weights as inter-node scheduling (Eq 40), ensuring
    a single source of truth for both normal scheduling and recovery.

    Score components (lower is better, same structure as inter_node.py):
      + W1 * T_wait   — queue occupancy estimate
      + W2 * L_j      — network latency
      + W3 * P_epc    — EPC pressure penalty
      + W4 * P_cap    — capability penalty
      + W5 * P_trust  — trust penalty
    """
    # Eq 35: T_wait from queue availability timestamps
    # For recovery, use queue_delay as a proxy (0 arrival = current time)
    T_wait = node.queue_delay(0.0)

    # Eq 36: EPC pressure — same quadratic-threshold model as inter_node.py
    P_epc = epc_pressure_penalty_ratio(node)

    # Eq 37: P_cap — capability penalty (lower capability → higher cost)
    # Normalized capability C_j is already in node.capability property
    P_cap = max(0.0, 1.0 - (node.capability / 100.0))

    # Eq 38: P_trust
    P_trust = 1.0 - node.trust

    # Eq 40: SpiderScore using config.py weights
    score = (config.W1_WAIT * T_wait
             + config.W2_LATENCY * node.network_ms
             + config.W3_EPC * P_epc
             + config.W4_CAP * P_cap
             + config.W5_TRUST * P_trust)

    return score


def epc_pressure_penalty_ratio(node: FogNode) -> float:
    """Eq 29: Sigmoid EPC pressure estimate for recovery scoring.

    Uses the same sigmoid model as inter_node.epc_pressure_penalty
    but operates on node-level utilization ratio instead of per-task.
    """
    import math
    # assigned_count / 10 is a rough proxy for EPC utilization
    utilization = min(1.0, node.assigned_count / max(1, 10))
    epsilon_j = 1.0 - utilization  # availability ratio
    rho_epc = 1.0 / (1.0 + math.exp(-config.EPC_KAPPA * (epsilon_j - config.EPC_PRESSURE_TAU)))
    return rho_epc * utilization


def select_recovery_node(
    states: List[FogNodeState],
    rng: np.random.Generator,
) -> Optional[FogNodeState]:
    """
    Eq 125: F_recover = argmin_{F_j in F_alive} SpiderScore(F_j, B_k)

    Selects the best alive node for recovery by scoring each node's
    :attr:`fog_node` with ``config.W*`` weights (lower is better).
    """
    candidates = [s for s in states
                  if s.is_alive and not s.declared_failed]
    if not candidates:
        return None

    best_state = None
    best_score = float("inf")
    for s in candidates:
        score = _recovery_spider_score(s.fog_node) + rng.uniform(0.0, 0.5)
        if score < best_score:
            best_score = score
            best_state = s
    return best_state


def simulate_failure_detection(
    n_nodes: int = 20,
    failure_rate: float = 0.1,
    seed: int = 20260424,
) -> dict:
    """
    Run a simulated failure detection scenario.
    Returns detection time, recovery metrics, and false positive rate.

    Each :class:`FogNodeState` composes a :class:`models.FogNode`
    reference — one list tracks both monitoring and scheduling state.
    """
    rng = np.random.default_rng(seed)

    # One list: each FogNodeState wraps a FogNode (single source of truth)
    fog_nodes = generate_nodes(n_nodes, heterogeneous=True, rng=rng)
    states = [FogNodeState(fog_node=fn) for fn in fog_nodes]

    # Partition into monitoring groups
    groups = partition_into_groups(states)

    # Set initial heartbeats
    for s in states:
        s.last_heartbeat_ms = 0.0

    # Inject failures
    n_failures = max(1, int(n_nodes * failure_rate))
    failed_indices = rng.choice(n_nodes, size=n_failures, replace=False)
    for idx in failed_indices:
        states[idx].is_alive = False
        # Failed nodes stop sending heartbeats (stale last_heartbeat)

    # Advance time past heartbeat timeout for live nodes
    current_ms = config.HEARTBEAT_TIMEOUT_MS + 20.0
    for s in states:
        if s.is_alive:
            s.last_heartbeat_ms = current_ms - rng.uniform(1, 10)

    # Run detection
    detected = detect_failures(groups, current_ms)

    # Recovery: select best alive node using SpiderScore (Eq 125)
    recovery = select_recovery_node(states, rng)

    # Compute metrics
    true_failed = set(int(i) for i in failed_indices)
    detected_set = set(detected)
    true_positives = detected_set & true_failed
    false_positives = detected_set - true_failed

    return {
        "n_nodes": n_nodes,
        "n_groups": len(groups),
        "n_injected_failures": n_failures,
        "n_detected": len(detected),
        "true_positive_rate": len(true_positives) / max(1, n_failures),
        "false_positive_rate": len(false_positives) / max(1, n_nodes - n_failures),
        "detection_time_ms": current_ms,
        "recovery_node_id": recovery.node_id if recovery else None,
    }

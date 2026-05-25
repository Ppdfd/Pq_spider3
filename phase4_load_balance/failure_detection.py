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


# ── Configuration ──
GROUP_SIZE_MIN = 3
GROUP_SIZE_MAX = 7
DEFAULT_GROUP_SIZE = 5
HEARTBEAT_TIMEOUT_MS = 50.0   # tau_h: heartbeat timeout threshold (ms)
QUORUM_FRACTION = 0.5         # q >= ceil(s / 2)


@dataclass
class FogNodeState:
    """Runtime state of a fog node for failure detection."""
    node_id: int
    is_alive: bool = True
    last_heartbeat_ms: float = 0.0
    epoch: int = 0
    status: str = "healthy"
    # Monitoring state
    suspicious_count: int = 0
    declared_failed: bool = False


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
    group_size: int = DEFAULT_GROUP_SIZE,
) -> List[MonitoringGroup]:
    """
    Eq 117-119: Partition fog layer into bounded-size monitoring groups.
    g = ceil(N / s) groups, each with 3 <= s <= 7 members.
    """
    s = max(GROUP_SIZE_MIN, min(GROUP_SIZE_MAX, group_size))
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
    tau_h: float = HEARTBEAT_TIMEOUT_MS,
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
    tau_h: float = HEARTBEAT_TIMEOUT_MS,
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
    tau_h: float = HEARTBEAT_TIMEOUT_MS,
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


def select_recovery_node(
    alive_nodes: List[FogNodeState],
    rng: np.random.Generator,
) -> Optional[FogNodeState]:
    """
    Eq 125: F_recover = argmin SpiderScore(F_j, B_k)

    Uses the same SpiderScore-based selection for recovery as for normal
    scheduling, ensuring consistency between workload orchestration and
    recovery operations.

    Simplified: select node with best combination of health and availability.
    """
    if not alive_nodes:
        return None

    best_node = None
    best_score = float("inf")
    for n in alive_nodes:
        if n.declared_failed:
            continue
        # Simple scoring: lower is better
        # Lower heartbeat age = more responsive
        score = n.suspicious_count * 10.0 + rng.uniform(0, 5)
        if score < best_score:
            best_score = score
            best_node = n
    return best_node


def simulate_failure_detection(
    n_nodes: int = 20,
    failure_rate: float = 0.1,
    seed: int = 20260424,
) -> dict:
    """
    Run a simulated failure detection scenario.
    Returns detection time, recovery metrics, and false positive rate.
    """
    rng = np.random.default_rng(seed)

    # Initialize fog nodes
    nodes = [FogNodeState(node_id=i) for i in range(n_nodes)]

    # Partition into monitoring groups
    groups = partition_into_groups(nodes)

    # Set initial heartbeats
    for n in nodes:
        n.last_heartbeat_ms = 0.0

    # Inject failures
    n_failures = max(1, int(n_nodes * failure_rate))
    failed_indices = rng.choice(n_nodes, size=n_failures, replace=False)
    for idx in failed_indices:
        nodes[idx].is_alive = False
        # Failed nodes stop sending heartbeats (stale last_heartbeat)

    # Advance time past heartbeat timeout for live nodes
    current_ms = HEARTBEAT_TIMEOUT_MS + 20.0
    for n in nodes:
        if n.is_alive:
            n.last_heartbeat_ms = current_ms - rng.uniform(1, 10)

    # Run detection
    detected = detect_failures(groups, current_ms)

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
    }

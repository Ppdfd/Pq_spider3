"""
Data Models for PQ-SPIDER Load Balancing Simulation
=====================================================

Dataclasses representing the core entities in the discrete-event
simulation: workload tasks, fog nodes, and TEE enclaves.
"""

from dataclasses import dataclass, field
from typing import List


@dataclass
class WorkloadTask:
    """Synthetic IIoT security micro-batch."""

    arrival_ms: float
    records: int
    attrs: int
    policy_depth: int
    payload_kb: float
    risk: float
    deadline_ms: float
    tee_work: float
    ree_work: float
    epc_req_mb: float

    @property
    def total_work(self) -> float:
        return self.tee_work + self.ree_work

    @property
    def crypto_intensity(self) -> float:
        return 0.65 * self.records + 0.38 * self.attrs + 2.2 * self.policy_depth


@dataclass
class FogNode:
    """Fog node with separate TEE and REE queues."""

    node_id: int
    tee_rate: float
    ree_rate: float
    network_ms: float
    epc_total_mb: float
    trust: float
    energy_factor: float
    tee_available_ms: float = 0.0
    ree_available_ms: float = 0.0
    assigned_count: int = 0
    policy_cached: bool = False
    kyber_cached: bool = False

    @property
    def capability(self) -> float:
        return 11.0 * self.tee_rate + 7.0 * self.ree_rate + 0.010 * self.epc_total_mb

    def queue_delay(self, arrival_ms: float) -> float:
        return 1.5 * max(0.0, (self.tee_available_ms + self.ree_available_ms) / 2.0 - arrival_ms)


@dataclass
class Enclave:
    """Single TEE enclave within a fog node (Eq 26 state model)."""

    enc_id: int
    service_rate: float       # µ_{j,k}  — ops/sec from OP-TEE benchmark
    epc_total: float          # M_total  — bytes
    epc_available: float      # M_free   — bytes (depletes per task)
    contention: float = 0.0   # ρ_{j,k}  — runtime contention
    queue_length: int = 0     # q_{j,k}  — current queue depth
    available_ms: float = 0.0 # earliest time enclave becomes free
    recent_count: int = 0     # workload affinity counter (Eq 45)
    _finish_times: List[float] = field(default_factory=list)  # exact completion times per task


def clone_nodes(nodes: List[FogNode]) -> List[FogNode]:
    """Deep-copy fog node list so each algorithm starts from identical state."""
    return [
        FogNode(
            node_id=n.node_id,
            tee_rate=n.tee_rate,
            ree_rate=n.ree_rate,
            network_ms=n.network_ms,
            epc_total_mb=n.epc_total_mb,
            trust=n.trust,
            energy_factor=n.energy_factor,
            tee_available_ms=n.tee_available_ms,
            ree_available_ms=n.ree_available_ms,
            assigned_count=n.assigned_count,
            policy_cached=n.policy_cached,
            kyber_cached=n.kyber_cached,
        )
        for n in nodes
    ]


def clone_enclaves(enclaves: List[Enclave]) -> List[Enclave]:
    """Deep-copy enclave list so each algorithm starts from identical state."""
    return [
        Enclave(
            enc_id=e.enc_id,
            service_rate=e.service_rate,
            epc_total=e.epc_total,
            epc_available=e.epc_available,   # preserve initial EPC usage
            contention=e.contention,
            queue_length=e.queue_length,      # preserve initial load
            available_ms=e.available_ms,
            recent_count=e.recent_count,
            _finish_times=list(e._finish_times),  # deep-copy finish times
        )
        for e in enclaves
    ]

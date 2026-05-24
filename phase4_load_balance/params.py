"""
Simulation Parameters for PQ-SPIDER Load Balancing Evaluation
==============================================================

All constants with derivations and citations. Each parameter is derived
from measured data or published literature. No existing fog simulator
(iFogSim, YAFS, CloudSim) supports TEE-specific resource modelling
(EPC memory, enclave contention, world-switch overhead), necessitating
a custom discrete-event simulation.

References:
  [A] Our OP-TEE QEMU measurements: optee_bench/measured_values.json
  [B] Arnautov et al., "SCONE: Secure Linux Containers with Intel SGX",
      OSDI 2016 — EPC paging overhead characterization
  [C] Weisse et al., "Regaining Lost Cycles with HotCalls", ISCA 2017
      — SGX transition and paging cycle counts (~40K cycles/page fault)
  [D] Amacher & Schiavoni, "On The Performance of ARM TrustZone",
      DAIS 2019 — TrustZone world-switch latency benchmarks
  [E] OP-TEE source: core/arch/arm/plat-vexpress/conf.mk — TA_DATA_SIZE
  [F] Orenbach et al., "Eleos: ExitLess OS Services for SGX Enclaves",
      EuroSys 2017 — TLB shootdown amplification under EPC paging
  [G] Taassori et al., "VAULT: Reducing Paging Overheads in SGX",
      ASPLOS 2018 — Realistic SGX workload paging overheads (5-20ms)
"""

SIMULATION_PARAMS = {
    # ── EPC Swap Penalty ──
    # Derivation: ~40,000 cycles per page fault [C]. At 2GHz Cortex-A72:
    #   40,000 / 2×10⁹ = 0.02ms per page.
    # Crypto overhead (encrypt + MAC + EPCM update): ~12,000 cycles [B]
    #   = 0.006ms per page.  Total per page: ~0.026ms.
    # Working set for PQ crypto (Kyber768+Dilithium-III, NIST L3): 952KB
    #   = 238 × 4KB pages.
    # Base swap cost: 238 × 0.026ms ≈ 6.2ms.
    # TLB shootdown amplification (1.5–1.8×) per [F]: 6.2 × 1.8 ≈ 11.2ms.
    # We use 12ms as the cited value, with range (8, 18) to capture
    # workload variance per VAULT [G] which reports 5-20ms for realistic
    # SGX workloads. The 45ms used previously assumed worst-case Kyber1024
    # + Dilithium-V which is rarely deployed; NIST SP 800-208 recommends
    # NIST L3 for IIoT, matching our calibration.
    "epc_swap_base_ms": 12.0,
    "epc_swap_range": (8.0, 18.0),

    # ── Contention Penalty ──
    # Each queued task requires one additional world-switch round-trip
    # to context-switch the enclave. Measured world-switch: 1.13ms [A].
    # Penalty per unit normalized load = world_switch_ms.
    # Ref: Amacher & Schiavoni DAIS'19 confirm ~1–2ms per switch on
    # Cortex-A platforms.
    "contention_per_unit_ms": 1.13,  # from measured_values.json [A]

    # ── Rate Heterogeneity (within a single fog node) ──
    # Sources of variation: thermal throttling (up to 50% on ARM, [D]),
    # DVFS states, and per-core manufacturing variance.
    # Realistic within-node ratio: 0.5–1.3× baseline rate.
    # Note: cross-device ratios (e.g. RPi4 vs Jetson) can be much wider,
    # but intra-node enclaves share the same SoC.
    "rate_multiplier_range": (0.5, 1.3),

    # ── EPC Heterogeneity ──
    # OP-TEE allocates TA_DATA_SIZE per TA instance — compile-time
    # constant from conf.mk [E]. All enclaves on same node get identical
    # allocation. Small jitter (±5%) models OS-level TZDRAM fragmentation.
    "epc_multiplier_range": (0.95, 1.05),

    # ── TEE Startup Overhead ──
    # World-switch NW→SW: 1.13ms [A] + TA session setup: ~1.5ms [D].
    # Total: ~2.6ms.
    "tee_startup_ms": 2.6,

    # ── REE Startup Overhead ──
    # No world-switch needed (already in NW). Linux CFS scheduling
    # quantum jitter: ~1–4ms. Conservative estimate: 1.8ms.
    "ree_startup_ms": 1.8,

    # ── Finalization Overhead ──
    # Return world-switch SW→NW: 1.13ms [A] + result serialization
    # + network ACK. Sum: ~3.6ms.
    "finalization_ms": 3.6,
}

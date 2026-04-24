"""
Real-time System Metrics Reader
================================
Replaces hardcoded hardware estimates with live measurements via `psutil`.
Used by Phase 1 (fog node init) and Phase 4 (scheduler contention/energy).

Provides:
  - CPU capability score from real freq/memory/cores
  - Network latency from actual localhost TCP RTT
  - Per-core CPU contention from real utilization
  - CPU-time-based energy estimation (TDP model)
"""

import os
import time
import socket
import psutil


class SystemProfiler:
    """Reads real hardware state for Spider++ inputs."""

    def __init__(self):
        self._freq_cache = None
        self._mem_cache = None
        self._rtt_cache = None
        self._contention_ts = 0.0
        self._cores = os.cpu_count() or 4

    def _get_freq(self):
        """Cached CPU frequency reading."""
        if self._freq_cache is None:
            freq = psutil.cpu_freq()
            self._freq_cache = freq.current if freq else 2400.0
        return self._freq_cache

    def _get_mem_mb(self):
        """Cached total memory in MB."""
        if self._mem_cache is None:
            mem = psutil.virtual_memory()
            self._mem_cache = mem.total / (1024 ** 2)
        return self._mem_cache

    def get_capability_score(self, node_id=0):
        """Eq 34: C_j from ACTUAL hardware.

        C = α1·CPU_MHz + α2·RAM_MB + α3·cores
        """
        cpu_mhz = self._get_freq()
        ram_mb = self._get_mem_mb()

        alpha1, alpha2, alpha3 = 0.05, 0.01, 5.0
        base = alpha1 * cpu_mhz + alpha2 * ram_mb + alpha3 * self._cores
        return int(base)

    def get_network_latency_ms(self):
        """Eq 36: L_j — actual measured localhost RTT (cached).

        Performs a real TCP connect to localhost to measure round-trip.
        Falls back to a UDP-based measurement if TCP fails.
        """
        if self._rtt_cache is not None:
            return self._rtt_cache
        # Try TCP connect to common ports
        for port in [22, 80, 8080, 443]:
            sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
            sock.settimeout(0.5)
            t0 = time.perf_counter()
            try:
                sock.connect(('127.0.0.1', port))
                latency_ms = (time.perf_counter() - t0) * 1000
                sock.close()
                self._rtt_cache = latency_ms
                return latency_ms
            except (ConnectionRefusedError, OSError):
                latency_ms = (time.perf_counter() - t0) * 1000
                sock.close()
                if latency_ms < 100:
                    self._rtt_cache = latency_ms
                    return latency_ms

        # Fallback: UDP loopback
        sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        t0 = time.perf_counter()
        try:
            sock.sendto(b'\x00', ('127.0.0.1', 55555))
        except OSError:
            pass
        latency_ms = (time.perf_counter() - t0) * 1000
        sock.close()
        self._rtt_cache = latency_ms
        return latency_ms

    def get_cpu_contention(self, core_id=None):
        """Eq 44: ρ — real CPU utilization from psutil.

        Uses a cached per-cpu snapshot (refreshed every 1s) to avoid
        repeated 50ms sleeps when called per-enclave.
        Returns value in [0.0, 1.0].
        """
        now = time.monotonic()
        # Cache per-CPU readings for 1 second
        if (not hasattr(self, '_contention_cache') or
                now - self._contention_ts > 1.0):
            self._contention_cache = psutil.cpu_percent(
                interval=0.05, percpu=True)
            self._contention_ts = now

        if core_id is not None:
            idx = core_id % len(self._contention_cache)
            return self._contention_cache[idx] / 100.0
        return sum(self._contention_cache) / len(self._contention_cache) / 100.0

    def get_cpu_times_snapshot(self):
        """Snapshot for energy measurement — returns (user, system) seconds."""
        proc = psutil.Process()
        t = proc.cpu_times()
        return t.user, t.system

    def estimate_energy_mj(self, cpu_time_seconds):
        """Energy from real CPU time × TDP estimate.

        Uses Apple Silicon or Intel TDP estimates based on platform.
        """
        import platform
        machine = platform.machine().lower()

        if 'arm' in machine or 'aarch64' in machine:
            # Apple M-series: ~15W total package TDP
            tdp_watts = 15.0
        else:
            # Intel/AMD: estimate ~65W
            tdp_watts = 65.0

        per_core_watts = tdp_watts / self._cores

        # Scale by actual freq vs nominal
        freq = psutil.cpu_freq()
        if freq and freq.max > 0:
            freq_scale = freq.current / freq.max
        else:
            freq_scale = 1.0

        joules = cpu_time_seconds * per_core_watts * freq_scale
        return joules * 1000  # convert to mJ

    def get_system_summary(self):
        """Return a dict summarizing all measured hardware values."""
        return {
            "cpu_freq_mhz":     self._get_freq(),
            "total_ram_mb":     round(self._get_mem_mb(), 1),
            "cpu_cores":        self._cores,
            "capability_score": self.get_capability_score(),
            "localhost_rtt_ms": round(self.get_network_latency_ms(), 4),
            "cpu_contention":   round(self.get_cpu_contention(), 4),
        }


if __name__ == "__main__":
    import json
    p = SystemProfiler()
    summary = p.get_system_summary()
    print(json.dumps(summary, indent=2))

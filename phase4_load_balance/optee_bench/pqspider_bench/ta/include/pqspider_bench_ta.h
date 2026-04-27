/* SPDX-License-Identifier: BSD-2-Clause */
/*
 * PQ-SPIDER Benchmark TA — Header
 *
 * Measures AES-256-GCM throughput and NW/SW context-switch latency
 * inside OP-TEE secure world for the Spider++ load balancer.
 */
#ifndef TA_PQSPIDER_BENCH_H
#define TA_PQSPIDER_BENCH_H

/*
 * UUID: c7f4e3a1-5b82-4d9f-a1c3-9e8d7f6b5a40
 * Generated for PQ-SPIDER project
 */
#define TA_PQSPIDER_BENCH_UUID \
	{ 0xc7f4e3a1, 0x5b82, 0x4d9f, \
		{ 0xa1, 0xc3, 0x9e, 0x8d, 0x7f, 0x6b, 0x5a, 0x40 } }

/*
 * CMD_BENCHMARK (0):
 *   params[0].value.a = number of AES-GCM iterations
 *   returns  params[1].value.a = elapsed milliseconds
 *            params[1].value.b = iterations completed
 *
 * CMD_NOP (1):
 *   No params. Returns immediately. Used to measure NW→SW latency.
 */
#define CMD_BENCHMARK		0
#define CMD_NOP			1
#define CMD_GET_ENCLAVE_STATE	2

#endif /* TA_PQSPIDER_BENCH_H */

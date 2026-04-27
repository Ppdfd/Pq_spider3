// SPDX-License-Identifier: BSD-2-Clause
/*
 * PQ-SPIDER Benchmark — Normal World Host Application
 *
 * Measures three values needed by Spider++ load balancer:
 *   1. SERVICE_RATE  — AES-256-GCM encrypt throughput (tasks/sec)
 *   2. NW_SW_LATENCY — Normal World → Secure World context switch (ms)
 *   3. TRUST_SCORE   — TA session open success rate (0.0-1.0)
 *
 * Output is printed to stdout AND written to /mnt/host/bench_results.json
 * so the PQ-Spider Python code on the host can read it via VirtFS.
 *
 * Usage:  pqspider_bench [iterations]
 *   iterations: number of AES-GCM ops (default: 100)
 */

#include <err.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <time.h>

#include <tee_client_api.h>
#include <pqspider_bench_ta.h>

#define LATENCY_ROUNDS   50
#define TRUST_ROUNDS     20
#define JSON_PATH        "/mnt/host/pq_spider/Pq_spider_new/phase4_load_balance/optee_bench/measured_values.json"

int main(int argc, char *argv[])
{
	TEEC_Result res;
	TEEC_Context ctx;
	TEEC_Session sess;
	TEEC_Operation op;
	TEEC_UUID uuid = TA_PQSPIDER_BENCH_UUID;
	uint32_t err_origin;
	uint32_t iterations = 100;

	if (argc > 1)
		iterations = (uint32_t)atoi(argv[1]);

	/* ── Initialize TEE context ── */
	res = TEEC_InitializeContext(NULL, &ctx);
	if (res != TEEC_SUCCESS)
		errx(1, "TEEC_InitializeContext failed: 0x%x", res);

	res = TEEC_OpenSession(&ctx, &sess, &uuid,
			       TEEC_LOGIN_PUBLIC, NULL, NULL, &err_origin);
	if (res != TEEC_SUCCESS)
		errx(1, "TEEC_OpenSession failed: 0x%x origin 0x%x",
		     res, err_origin);

	/* ═══════════════════════════════════════════════════════
	 * 1. SERVICE_RATE: AES-256-GCM throughput
	 * ═══════════════════════════════════════════════════════ */
	memset(&op, 0, sizeof(op));
	op.paramTypes = TEEC_PARAM_TYPES(TEEC_VALUE_INOUT, TEEC_VALUE_OUTPUT,
					 TEEC_NONE, TEEC_NONE);
	op.params[0].value.a = iterations;

	res = TEEC_InvokeCommand(&sess, CMD_BENCHMARK, &op, &err_origin);
	if (res != TEEC_SUCCESS)
		errx(1, "CMD_BENCHMARK failed: 0x%x origin 0x%x",
		     res, err_origin);

	uint32_t elapsed_ms = op.params[1].value.a;
	uint32_t iters_done = op.params[1].value.b;

	/* ═══════════════════════════════════════════════════════
	 * 1.5 GET_ENCLAVE_STATE (Equation 26)
	 * ═══════════════════════════════════════════════════════ */
	memset(&op, 0, sizeof(op));
	op.paramTypes = TEEC_PARAM_TYPES(TEEC_VALUE_OUTPUT, TEEC_VALUE_OUTPUT,
					 TEEC_VALUE_OUTPUT, TEEC_VALUE_OUTPUT);
	res = TEEC_InvokeCommand(&sess, CMD_GET_ENCLAVE_STATE, &op, &err_origin);
	if (res != TEEC_SUCCESS)
		errx(1, "CMD_GET_ENCLAVE_STATE failed: 0x%x origin 0x%x",
		     res, err_origin);

	uint32_t queue_length = op.params[0].value.a;
	uint32_t service_rate = op.params[1].value.a;
	uint32_t epc_free = op.params[2].value.a;
	uint32_t contention = op.params[3].value.a;

	printf("ENCLAVE_STATE(Eq 26): q=%u, mu=%u ops/s, M_free=%u B, rho=%u\n",
	       queue_length, service_rate, epc_free, contention);

	/* ═══════════════════════════════════════════════════════
	 * 2. NW_SW_LATENCY: world-switch round trip
	 * ═══════════════════════════════════════════════════════ */
	double total_lat_ms = 0.0;
	for (int i = 0; i < LATENCY_ROUNDS; i++) {
		struct timespec t0, t1;
		memset(&op, 0, sizeof(op));
		op.paramTypes = TEEC_PARAM_TYPES(TEEC_NONE, TEEC_NONE,
						 TEEC_NONE, TEEC_NONE);
		clock_gettime(CLOCK_MONOTONIC, &t0);
		TEEC_InvokeCommand(&sess, CMD_NOP, &op, &err_origin);
		clock_gettime(CLOCK_MONOTONIC, &t1);
		total_lat_ms += (t1.tv_sec - t0.tv_sec) * 1000.0
			      + (t1.tv_nsec - t0.tv_nsec) / 1e6;
	}
	float avg_latency = (float)(total_lat_ms / LATENCY_ROUNDS);
	printf("NW_SW_LATENCY_MS=%.4f  (avg of %d rounds)\n",
	       avg_latency, LATENCY_ROUNDS);

	TEEC_CloseSession(&sess);

	/* ═══════════════════════════════════════════════════════
	 * 3. TRUST_SCORE: session open success rate
	 * ═══════════════════════════════════════════════════════ */
	int success = 0;
	for (int i = 0; i < TRUST_ROUNDS; i++) {
		TEEC_Session test_sess;
		res = TEEC_OpenSession(&ctx, &test_sess, &uuid,
				       TEEC_LOGIN_PUBLIC, NULL, NULL,
				       &err_origin);
		if (res == TEEC_SUCCESS) {
			success++;
			TEEC_CloseSession(&test_sess);
		}
	}
	float trust_score = (float)success / (float)TRUST_ROUNDS;
	printf("TRUST_SCORE=%.4f  (%d/%d sessions OK)\n",
	       trust_score, success, TRUST_ROUNDS);

	TEEC_FinalizeContext(&ctx);

	/* ═══════════════════════════════════════════════════════
	 * Write JSON results to VirtFS shared path
	 * ═══════════════════════════════════════════════════════ */
	FILE *fp = fopen(JSON_PATH, "w");
	if (fp) {
		fprintf(fp,
			"{\n"
			"  \"service_rate\": %u,\n"
			"  \"queue_length\": %u,\n"
			"  \"epc_free\": %u,\n"
			"  \"contention\": %u,\n"
			"  \"world_switch_ms\": %.4f,\n"
			"  \"trust_score\": %.4f,\n"
			"  \"iterations\": %u,\n"
			"  \"elapsed_ms\": %u,\n"
			"  \"source\": \"pqspider_bench TA on OP-TEE QEMU v8\"\n"
			"}\n",
			service_rate, queue_length, epc_free, contention,
			avg_latency, trust_score, iters_done, elapsed_ms);
		fclose(fp);
		printf("\nResults written to %s\n", JSON_PATH);
	} else {
		printf("\nWARNING: Could not write to %s\n", JSON_PATH);
		printf("Make sure VirtFS is mounted: mount -t 9p -o trans=virtio host /mnt/host\n");
	}

	return 0;
}

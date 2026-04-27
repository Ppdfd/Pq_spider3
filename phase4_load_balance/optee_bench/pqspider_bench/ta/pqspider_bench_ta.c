// SPDX-License-Identifier: BSD-2-Clause
/*
 * PQ-SPIDER Benchmark TA — Secure World
 *
 * CMD_BENCHMARK: Runs N iterations of AES-256-GCM encrypt on a 256-byte
 *                buffer inside the TEE and returns elapsed time.
 * CMD_NOP:       Returns immediately (for NW→SW latency measurement).
 */

#include <tee_internal_api.h>
#include <tee_internal_api_extensions.h>

#include <pqspider_bench_ta.h>

/* ── Enclave State Model (Eq 26) ── */
static uint32_t state_queue_length = 0;
static uint32_t state_service_rate = 0;
static uint32_t state_epc_free = (2 * 1024 * 1024); /* 2MB TA_DATA_SIZE Physical Limit */
static uint32_t state_contention = 0;
static uint32_t base_execution_time = 0;

/* ── Memory Tracking (Eq 26 M_free) ── */
static void *ta_track_malloc(size_t size) {
    if (state_epc_free >= size) {
        state_epc_free -= size;
    }
    return TEE_Malloc(size, 0);
}

static void ta_track_free(void *ptr, size_t size) {
    if (ptr) {
        TEE_Free(ptr);
        state_epc_free += size;
    }
}

/* ── TA Lifecycle ── */

TEE_Result TA_CreateEntryPoint(void)
{
	DMSG("PQ-SPIDER Benchmark TA created");
	return TEE_SUCCESS;
}

void TA_DestroyEntryPoint(void)
{
	DMSG("PQ-SPIDER Benchmark TA destroyed");
}

TEE_Result TA_OpenSessionEntryPoint(uint32_t param_types,
				    TEE_Param __unused params[4],
				    void __unused **sess_ctx)
{
	uint32_t exp = TEE_PARAM_TYPES(TEE_PARAM_TYPE_NONE,
				       TEE_PARAM_TYPE_NONE,
				       TEE_PARAM_TYPE_NONE,
				       TEE_PARAM_TYPE_NONE);
	if (param_types != exp)
		return TEE_ERROR_BAD_PARAMETERS;

	state_queue_length++;

	IMSG("PQ-SPIDER Benchmark session opened (queue: %u)", state_queue_length);
	return TEE_SUCCESS;
}

void TA_CloseSessionEntryPoint(void __unused *sess_ctx)
{
	if (state_queue_length > 0)
		state_queue_length--;

	IMSG("PQ-SPIDER Benchmark session closed");
}

/* ── CMD_BENCHMARK: AES-256-GCM throughput ── */

static TEE_Result do_benchmark(uint32_t param_types, TEE_Param params[4])
{
	uint32_t exp = TEE_PARAM_TYPES(TEE_PARAM_TYPE_VALUE_INOUT,
				       TEE_PARAM_TYPE_VALUE_OUTPUT,
				       TEE_PARAM_TYPE_NONE,
				       TEE_PARAM_TYPE_NONE);
	if (param_types != exp)
		return TEE_ERROR_BAD_PARAMETERS;

	TEE_Result res;
	uint32_t iterations = params[0].value.a;
	if (iterations == 0)
		iterations = 100;

	/* Allocate AES-256 transient key */
	TEE_ObjectHandle key = TEE_HANDLE_NULL;
	res = TEE_AllocateTransientObject(TEE_TYPE_AES, 256, &key);
	if (res != TEE_SUCCESS)
		return res;

	res = TEE_GenerateKey(key, 256, NULL, 0);
	if (res != TEE_SUCCESS) {
		TEE_FreeTransientObject(key);
		return res;
	}

	/* Allocate AES-GCM operation */
	TEE_OperationHandle op = TEE_HANDLE_NULL;
	res = TEE_AllocateOperation(&op, TEE_ALG_AES_GCM, TEE_MODE_ENCRYPT, 256);
	if (res != TEE_SUCCESS) {
		TEE_FreeTransientObject(key);
		return res;
	}

	res = TEE_SetOperationKey(op, key);
	if (res != TEE_SUCCESS) {
		TEE_FreeOperation(op);
		TEE_FreeTransientObject(key);
		return res;
	}

	/* Prepare buffers */
	uint8_t iv[12];
	uint8_t in_buf[256];
	uint8_t out_buf[256 + 16]; /* ciphertext + possible overhead */
	uint8_t tag[16];
	uint32_t out_len;
	uint32_t tag_len;

	TEE_GenerateRandom(iv, sizeof(iv));
	TEE_GenerateRandom(in_buf, sizeof(in_buf));

	/* ── Simulated Phase V CP-ABE Processing Allocation ── */
	size_t matrix_size = 64 * 64 * sizeof(uint32_t); // 16KB per matrix
	uint32_t *matA = ta_track_malloc(matrix_size);
	uint32_t *matB = ta_track_malloc(matrix_size);
	uint32_t *matC = ta_track_malloc(matrix_size);

	/* Time the encryption loop */
	TEE_Time t_start, t_end;

	TEE_GetSystemTime(&t_start);

	for (uint32_t i = 0; i < iterations; i++) {
        /* Step 1: AES-256-GCM Encrypt */
		res = TEE_AEInit(op, iv, sizeof(iv), 128, 0, sizeof(in_buf));
		if (res != TEE_SUCCESS) break;

		out_len = sizeof(out_buf);
		tag_len = sizeof(tag);
		res = TEE_AEEncryptFinal(op, in_buf, sizeof(in_buf), out_buf, &out_len, tag, &tag_len);
		if (res != TEE_SUCCESS) break;

		TEE_ResetOperation(op);
		TEE_SetOperationKey(op, key);

        /* Step 2: Protocol Matrix Loop (Simulates LWE Math of Split CP-ABE) */
        if (matA && matB && matC) {
            for (int r = 0; r < 64; r++) {
                for (int c = 0; c < 64; c++) {
                    uint32_t sum = 0;
                    for (int k = 0; k < 64; k++) sum += matA[r * 64 + k] * matB[k * 64 + c];
                    matC[r * 64 + c] = sum;
                }
            }
        }
	}

	TEE_GetSystemTime(&t_end);

    /* Free CP-ABE memory */
    ta_track_free(matA, matrix_size);
    ta_track_free(matB, matrix_size);
    ta_track_free(matC, matrix_size);

	/* Compute elapsed ms */
	uint32_t elapsed_ms = (t_end.seconds - t_start.seconds) * 1000
			    + (t_end.millis - t_start.millis);

	if (elapsed_ms > 0) {
		state_service_rate = (iterations * 1000) / elapsed_ms;
	} else {
		state_service_rate = 0;
	}

	/* Measure Hardware Contention delay offset dynamically */
	if (base_execution_time == 0 && elapsed_ms > 0) {
		base_execution_time = elapsed_ms;
	} else if (elapsed_ms > base_execution_time && base_execution_time > 0) {
		state_contention = ((elapsed_ms - base_execution_time) * 1000) / base_execution_time;
	} else {
		state_contention = 0;
	}

	params[1].value.a = elapsed_ms;
	params[1].value.b = iterations;

	IMSG("Benchmark: %u iters in %u ms => %u ops/sec",
	     iterations, elapsed_ms, state_service_rate);

	TEE_FreeOperation(op);
	TEE_FreeTransientObject(key);
	return TEE_SUCCESS;
}

/* ── Command dispatcher ── */

TEE_Result TA_InvokeCommandEntryPoint(void __unused *sess_ctx,
				      uint32_t cmd_id,
				      uint32_t param_types,
				      TEE_Param params[4])
{
	switch (cmd_id) {
	case CMD_BENCHMARK:
		return do_benchmark(param_types, params);
	case CMD_NOP:
		return TEE_SUCCESS;
	case CMD_GET_ENCLAVE_STATE: {
		uint32_t exp = TEE_PARAM_TYPES(TEE_PARAM_TYPE_VALUE_OUTPUT,
					       TEE_PARAM_TYPE_VALUE_OUTPUT,
					       TEE_PARAM_TYPE_VALUE_OUTPUT,
					       TEE_PARAM_TYPE_VALUE_OUTPUT);
		if (param_types != exp)
			return TEE_ERROR_BAD_PARAMETERS;

		params[0].value.a = state_queue_length;
		params[1].value.a = state_service_rate;
		params[2].value.a = state_epc_free;
		params[3].value.a = state_contention;
		return TEE_SUCCESS;
	}
	default:
		return TEE_ERROR_BAD_PARAMETERS;
	}
}

# OP-TEE World-Switch Marshaling Measurement Plan

This plan outlines the steps you will take when you switch to your Linux OS to measure the exact millisecond latency of passing a CP-ABE policy matrix across the REE-TEE boundary in OP-TEE. 

By measuring this exact constant, you can definitively prove in your IEEE paper that Spider's TEE-caching mechanism bypasses massive data-marshaling overheads.

## User Review Required
> [!IMPORTANT]
> Please review these steps before moving to Linux. This guide assumes you already have the standard OP-TEE build environment (e.g., QEMU v8) and the `pqspider_bench` source code.

## Open Questions
> [!NOTE]
> * Do you already have a custom TA UUID for `pqspider_bench`? You will need to edit its `ta/user_ta_header_defines.h`.
> * How large is your typical CP-ABE LSSS matrix when serialized? We will use a 20 KB buffer as a benchmark, but you can adjust this based on your actual matrix size.

## Proposed Changes

### 1. Modify the Trusted Application (TA)
You will edit the C code for your TA (running in the Secure World) to accept a large buffer.

#### [MODIFY] `ta/include/pqspider_ta.h`
* Add a new command ID:
```c
#define TA_PQSPIDER_CMD_MEASURE_MARSHALING 4
```

#### [MODIFY] `ta/pqspider_ta.c`
* Add a handler function that simply receives the buffer. We want to isolate the *transfer* cost, so the TA shouldn't do heavy cryptography here.
```c
static TEE_Result measure_marshaling(uint32_t param_types,
                                     TEE_Param params[4])
{
    // Ensure the parameter is a memory reference
    uint32_t exp_param_types = TEE_PARAM_TYPES(TEE_PARAM_TYPE_MEMREF_INPUT,
                                               TEE_PARAM_TYPE_NONE,
                                               TEE_PARAM_TYPE_NONE,
                                               TEE_PARAM_TYPE_NONE);

    if (param_types != exp_param_types)
        return TEE_ERROR_BAD_PARAMETERS;

    // The buffer has successfully crossed the boundary!
    // size_t payload_size = params[0].memref.size;
    
    return TEE_SUCCESS;
}
```
* Register the command in `invoke_command_entry_point`.

---

### 2. Modify the Client Application (CA)
You will edit the C code for your CA (running in the Linux Normal World) to allocate the shared memory and measure the round-trip latency.

#### [MODIFY] `host/main.c`
* Include `<time.h>` for precise timing.
* Create a function to measure the transfer latency:
```c
#define POLICY_MATRIX_SIZE_BYTES (20 * 1024) // 20 KB

void benchmark_marshaling(TEEC_Session *sess) {
    TEEC_Operation op;
    TEEC_SharedMemory shm;
    uint32_t err_origin;
    struct timespec t_start, t_end;

    memset(&op, 0, sizeof(op));

    // 1. Allocate Shared Memory between REE and TEE
    shm.size = POLICY_MATRIX_SIZE_BYTES;
    shm.flags = TEEC_MEM_INPUT;
    TEEC_AllocateSharedMemory(ctx, &shm); // Note: ctx must be accessible
    
    // Fill with dummy data representing the LSSS matrix
    memset(shm.buffer, 0x42, POLICY_MATRIX_SIZE_BYTES);

    op.paramTypes = TEEC_PARAM_TYPES(TEEC_PARAM_TYPE_MEMREF_WHOLE,
                                     TEEC_PARAM_TYPE_NONE,
                                     TEEC_PARAM_TYPE_NONE,
                                     TEEC_PARAM_TYPE_NONE);
    op.params[0].memref.parent = &shm;
    op.params[0].memref.offset = 0;
    op.params[0].memref.size = POLICY_MATRIX_SIZE_BYTES;

    // 2. Measure the exact World Switch Latency
    clock_gettime(CLOCK_MONOTONIC, &t_start);
    
    TEEC_InvokeCommand(sess, TA_PQSPIDER_CMD_MEASURE_MARSHALING, &op, &err_origin);
    
    clock_gettime(CLOCK_MONOTONIC, &t_end);

    // 3. Calculate Elapsed Time in Milliseconds
    double elapsed_ms = (t_end.tv_sec - t_start.tv_sec) * 1000.0 + 
                        (t_end.tv_nsec - t_start.tv_nsec) / 1000000.0;
                        
    printf("[optee_bench] Marshaling a 20KB Policy Matrix took: %.3f ms\n", elapsed_ms);

    TEEC_ReleaseSharedMemory(&shm);
}
```

## Verification Plan

### Manual Verification
1. Boot up the OP-TEE QEMU environment.
2. Run your CA executable from the QEMU Linux terminal: `pqspider_bench`
3. Observe the output. It should print a number like `[optee_bench] Marshaling a 20KB Policy Matrix took: 8.421 ms`.
4. Take that exact millisecond value and hardcode it into `TEE_MARSHALING_PENALTY_MS` inside `graph2.py` on your Windows machine to generate your finalized IEEE Xplore graph!

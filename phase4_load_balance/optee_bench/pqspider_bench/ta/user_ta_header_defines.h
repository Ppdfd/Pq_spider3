/* SPDX-License-Identifier: BSD-2-Clause */
/*
 * PQ-SPIDER Benchmark TA — Header Defines
 */

#ifndef USER_TA_HEADER_DEFINES_H
#define USER_TA_HEADER_DEFINES_H

#include <pqspider_bench_ta.h>

#define TA_UUID				TA_PQSPIDER_BENCH_UUID

#define TA_FLAGS			(TA_FLAG_MULTI_SESSION)

/* 8 KB stack — needed for AES-GCM operation handles */
#define TA_STACK_SIZE			(8 * 1024)

/* 2 MB heap — true physical tracking for M_free (Eq 26) */
#define TA_DATA_SIZE			(2 * 1024 * 1024)

#define TA_VERSION	"1.0"

#define TA_DESCRIPTION	"PQ-SPIDER Benchmark TA: AES-GCM throughput + NW/SW latency"

#endif /* USER_TA_HEADER_DEFINES_H */

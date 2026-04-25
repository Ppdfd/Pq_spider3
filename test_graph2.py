import numpy as np
from evaluation.spiderpp_full_evaluation import simulate_cache_latency

seed = 42
for task_count in [100, 600, 1200]:
    no_lat, no_hit = simulate_cache_latency(task_count, "no_cache", seed)
    rand_lat, rand_hit = simulate_cache_latency(task_count, "random_cache", seed)
    spider_lat, spider_hit = simulate_cache_latency(task_count, "spider_cache", seed)
    
    print(f"Tasks: {task_count}")
    print(f"  No Cache   | Lat: {no_lat:.1f} | Hit: {no_hit:.2f}")
    print(f"  Rand Cache | Lat: {rand_lat:.1f} | Hit: {rand_hit:.2f}")
    print(f"  Spider++   | Lat: {spider_lat:.1f} | Hit: {spider_hit:.2f}")


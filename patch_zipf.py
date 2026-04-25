import re

content = open("evaluation/spiderpp_full_evaluation.py").read()

old_zipf = re.search(r"def select_policy\(rng: np\.random\.Generator\) -> int:.*?return int\(rng\.choice\(policies, p=weights / weights\.sum\(\)\)\)", content, re.DOTALL).group(0)

new_zipf = """def select_policy(rng: np.random.Generator) -> int:
    \"\"\"Zipf-like policy locality: a few policies are reused frequently.\"\"\"
    n_policies = 50
    policies = np.arange(n_policies)
    # Zipf distribution: P(x) ~ 1 / x^s
    s = 1.05
    weights = 1.0 / (np.arange(1, n_policies + 1) ** s)
    return int(rng.choice(policies, p=weights / weights.sum()))"""

content = content.replace(old_zipf, new_zipf)
open("evaluation/spiderpp_full_evaluation.py", "w").write(content)

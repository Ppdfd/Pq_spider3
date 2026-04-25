import re

content = open("evaluation/spiderpp_full_evaluation.py").read()

content = content.replace("node.touch_policy(policy_id)", 'if mode == "spider_cache":\n            node.touch_policy(policy_id)')

open("evaluation/spiderpp_full_evaluation.py", "w").write(content)

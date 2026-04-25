import re

content = open("evaluation/spiderpp_full_evaluation.py").read()

content = content.replace("random.sample(range(12), 4)", "random.sample(range(50), 4)")
content = content.replace("random.sample([0, 1, 2, 3, 4, 5], 4)", "random.sample(range(50), 4)")

open("evaluation/spiderpp_full_evaluation.py", "w").write(content)

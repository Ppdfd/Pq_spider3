---
name: audit-fairness
description: >-
  Use when the user asks to check, audit, or verify the fairness, bias, or correctness of the evaluation graphs or simulation code.
---

# Instructions

1. **Check for Hardcoded Data**: Scan graph scripts to ensure they are not using hardcoded arrays (e.g., `np.array([485, 268, ...])`) for their metrics. All evaluation data must be derived from a mathematical model or a simulation engine.
2. **Verify Baseline Handicaps**: Check how the baseline algorithms are modeled.
   - Are they receiving the same task stream?
   - Do they share the same fog node capability stats?
   - Is the telemetry delay identical across all methods?
3. **Verify Failure-Rate Responsiveness**: When checking fault tolerance graphs (e.g. Graph 10), ensure that metrics like detection time, false positive rate, and control overhead correctly scale with the failure rate. Flat lines are usually indicative of synthetic bias.
4. **Verify whether it is correctly derive from papers**
checking if the graphs or simulation code are correctly derived from the papers.
5. **Report Findings**: If bias is found, write an honest audit report using the `analysis_results.md` artifact, clearly separating what is fair and what is flawed.
write it in structure
-overview
-report what is the difference from papers
-report what is not correctly derive from papers
-suggestion to fix

## Constraints
- **Never** hide or downplay bias in the codebase. If Spider-FT has an unfair advantage, explicitly call it out.
- **Never** fix bias by breaking the core architectural logic. Fix it by making the simulation environment uniform for all competitors.

## References
- See [analysis_results.md](../../brain/a08efeee-5059-40bb-b82b-46c11ec436e2/analysis_results.md) for a historical example of a strict fairness audit.

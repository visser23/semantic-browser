# Comparative analysis (10 major sites, median)

Date: 2026-03-11  
Methods compared:
- Standard browser use (default OpenClaw snapshot)
- OpenClaw ARIA snapshot
- Semantic Browser (auto route + planner payload)

## Median metrics

| Method | Median speed (ms) | Median token-in | Median token-out | Median accuracy* |
|---|---:|---:|---:|---:|
| Standard browser use | 1208.3 | 2437.5 | N/A (not measured) | 0.83 |
| OpenClaw ARIA snapshot | 914.5 | 20651.5 | N/A (not measured) | 1.0 |
| Semantic Browser (auto + planner) | 2146.5 | 586.0 | N/A (not measured) | 1.0 |

\*Accuracy is a keyword/task-term proxy per site (not full end-to-end action-set success).

## Per-site snapshot

| Site | Standard tok-in | ARIA tok-in | Semantic tok-in | Standard acc | ARIA acc | Semantic acc | Semantic route |
|---|---:|---:|---:|---:|---:|---:|---|
| amazon | 27816 | 50746 | 664 | 1.0 | 1.0 | 1.0 | aria_compact |
| youtube | 1220 | 5371 | 370 | 0.67 | 0.67 | 0.67 | aria_compact |
| reddit | 11580 | 44482 | 655 | 0.67 | 0.67 | 0.33 | aria_compact |
| linkedin | 2414 | 3682 | 572 | 1.0 | 1.0 | 1.0 | aria_compact |
| instagram | 35 | 292 | 590 | 0.0 | 0.0 | 0.67 | aria_compact |
| x | 2461 | 38016 | 582 | 1.0 | 1.0 | 1.0 | aria_compact |
| google_maps | 1928 | 6814 | 575 | 0.67 | 0.67 | 0.67 | aria_compact |
| notion | 348 | 22076 | 424 | 0.67 | 1.0 | 1.0 | aria_compact |
| wikipedia | 4626 | 19227 | 659 | 1.0 | 1.0 | 1.0 | aria_compact |
| bbc | 32928 | 48913 | 637 | 1.0 | 1.0 | 1.0 | aria_compact |

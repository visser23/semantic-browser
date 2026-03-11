# Action-set benchmark (10 sites, 20 tasks)

Methods:
- Standard browser use (raw page text + naive click-by-text)
- OpenClaw browser (snapshot refs + click)
- Semantic Browser (auto route + planner action IDs)

| Method | Success rate | Stuck rate | Median speed ms | Median tok-in | Median tok-out |
|---|---:|---:|---:|---:|---:|
| Standard browser use | 0.45 | 0.55 | 5198.1 | 144.5 | 14.0 |
| OpenClaw browser | 0.25 | 0.75 | 27336.5 | 46.5 | 6.5 |
| Semantic Browser | 0.35 | 0.65 | 30000.0 | 476.0 | 6.5 |
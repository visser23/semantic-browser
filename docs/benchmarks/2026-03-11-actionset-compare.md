# Action-set benchmark (10 sites, 20 tasks)

Methods:
- Standard browser use (raw page text + naive click-by-text)
- OpenClaw browser (snapshot refs + click)
- Semantic Browser (auto route + planner action IDs)

| Method | Success rate | Stuck rate | Median speed ms | Median tok-in | Median tok-out |
|---|---:|---:|---:|---:|---:|
| Standard browser use | 0.75 | 0.25 | 2491.1 | 268.0 | 13.0 |
| OpenClaw browser | 0.65 | 0.35 | 2557.9 | 2644.0 | 13.0 |
| Semantic Browser | 0.5 | 0.5 | 3633.2 | 920.0 | 13.0 |
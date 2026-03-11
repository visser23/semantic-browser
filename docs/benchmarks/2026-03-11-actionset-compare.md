# End-to-end benchmark (5 complex public-site tasks)

Methods compared per task request:
- Standard browser tooling (raw DOM extraction + JS actions)
- OpenClaw browser tooling (snapshot refs + browser actions)
- Semantic Browser (observe/act with semantic action IDs)

Planner route: `openai:gpt-4.1-mini` (same for all methods)

Cost model: Sonnet 4.6 estimated pricing constants (input $3.00 / 1M, output $15.00 / 1M).

| Method | Success rate | Failures | Median speed ms | Median tok-in | Median tok-out | Est. cost/request (USD) |
|---|---:|---:|---:|---:|---:|---:|
| Standard browser tooling | 0.2 | 4 | 13528.8 | 21592.0 | 99.0 | 0.046537 |
| OpenClaw browser tooling | 0.0 | 5 | 14805.3 | 14278.0 | 125.0 | 0.043909 |
| Semantic Browser | 0.4 | 3 | 16497.1 | 9958.0 | 113.0 | 0.033961 |

## Tasks

- **amazon_deals_electronics** (amazon): Open Today's Deals, then navigate to Electronics deals.
- **reddit_popular_askreddit** (reddit): Open the Popular feed, then open r/AskReddit.
- **youtube_explore_trending** (youtube): Open Explore, then open Trending.
- **bbc_news_technology** (bbc): Open BBC News, then open the Technology section.
- **wikipedia_english_current_events** (wikipedia): Open English Wikipedia, then open Current events.

Artifacts: `docs/benchmarks/2026-03-11-actionset-compare.md` and `docs/benchmarks/2026-03-11-actionset-compare.json`
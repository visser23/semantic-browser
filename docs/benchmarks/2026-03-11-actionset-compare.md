# End-to-end benchmark (25 AI-driven multi-step public-site tasks)

Methods compared per task request:
- Standard browser tooling (raw DOM extraction + JS actions)
- OpenClaw browser tooling (snapshot refs + browser actions)
- Semantic Browser (observe/act with semantic action IDs)

Each method ran the exact same 25 prompts and used the same planner model route.
Planner route: `openai:gpt-5.3-codex`

Cost model: Sonnet 4.6 estimated pricing constants (input $3.00 / 1M, output $15.00 / 1M).

Metric basis (apples-to-apples across all three methods):
- `planner input tokens (billable)`: tokens billed as planner input by the LLM provider.
- `planner output tokens (billable)`: tokens billed as planner output by the LLM provider.
- `browser/runtime payload bytes`: UTF-8 byte size of observation payload returned from browser/runtime and sent to planner.
- `browser/runtime payload token-estimate` (estimated): payload character count ÷ 4 (non-billable estimate).
- `total effective context load` (estimated): planner input tokens + payload token-estimate.
- `planner tool calls`: LLM-declared tool/function calls returned by planner API response payloads.
- `browser/runtime calls`: browser operations issued by each method loop (navigate/observe/act/open/close/evaluate/click/type/press).
- `total tool calls`: planner tool calls + browser/runtime calls.
- `indicative planner cost/request`: Sonnet 4.6-normalised cost from planner billable tokens only.

| Method | Success rate | Failures | Median speed ms | Planner in (billable) | Planner out (billable) | Browser payload bytes | Payload token-est (estimated) | Total effective context load (estimated) | Median planner tool calls | Median browser/runtime calls | Median total tool calls | Median total tool calls (success-only) | Indicative planner cost/request (USD) |
|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|
| Standard browser tooling | 0.24 | 19 | 11819.8 | 10118.0 | 74.0 | 27765.0 | 6918.0 | 17224.0 | 0.0 | 6.0 | 6.0 | 4.0 | 0.041005 |
| OpenClaw browser tooling | 0.72 | 7 | 10514.2 | 6833.0 | 66.0 | 20870.0 | 5219.0 | 12078.0 | 0.0 | 6.0 | 6.0 | 6.0 | 0.022053 |
| Semantic Browser | 0.48 | 13 | 24514.5 | 2596.0 | 35.0 | 4912.0 | 1231.0 | 3870.0 | 0.0 | 14.0 | 14.0 | 4.0 | 0.006195 |

## Cost summary (planner billable only; Sonnet 4.6-normalised)

| Method | Requests | Total indicative planner cost (USD) | Average/request (USD) |
|---|---:|---:|---:|
| Standard browser tooling | 25 | 1.025136 | 0.041005 |
| OpenClaw browser tooling | 25 | 0.551322 | 0.022053 |
| Semantic Browser | 25 | 0.154866 | 0.006195 |
| **Cross-method grand total** | **75** | **1.731324** | **0.023084** |

Concise readout:
- OpenClaw browser tooling improved success materially vs standard tooling (72% vs 24%) while reducing indicative planner cost/request by about 46%.
- Semantic Browser reduced planner spend sharply (~85% lower than standard; ~72% lower than OpenClaw), but with lower success than OpenClaw in this run (48%).
- Cost figures are planner-billable-only and do not include browser/runtime infrastructure costs.

## Per-run journals

- JSON journals directory: `docs/benchmarks/journals/2026-03-12`
- One journal file is written for every method x task run (75 files total).

## Tasks

- **bbc_news_tech** (bbc): Navigate to the BBC News Technology section.
- **wikipedia_current_events** (wikipedia): Open English Wikipedia, then navigate to Current events.
- **github_explore_trending** (github): Navigate to the Explore page, then open Trending repositories.
- **reddit_askreddit** (reddit): Navigate to r/AskReddit.
- **youtube_trending** (youtube): Navigate to the Trending page.
- **google_search_python** (google): Search for 'python web scraping tutorial' and wait for results.
- **wikipedia_search_alan_turing** (en): Search Wikipedia for 'Alan Turing' and open the article.
- **github_search_repo** (github): Search GitHub for 'playwright python' and view results.
- **amazon_search_headphones** (amazon): Search Amazon for 'wireless headphones'.
- **stackoverflow_search_async** (stackoverflow): Search Stack Overflow for 'python async await'.
- **bbc_sport_football** (bbc): Navigate to BBC Sport, then to the Football section.
- **amazon_deals** (amazon): Navigate to Today's Deals page.
- **wikipedia_random_article** (en): Click 'Random article' to go to a random Wikipedia article.
- **github_new_issue_page** (github): Navigate to the Issues tab of this repository.
- **hackernews_newest** (news): Navigate to the 'new' submissions page.
- **imdb_top_movies** (imdb): Navigate to the Top 250 Movies chart.
- **mdn_css_grid** (developer): Search MDN for 'CSS Grid' and open the CSS Grid Layout guide.
- **python_docs_asyncio** (docs): Navigate to the asyncio library documentation.
- **google_images_search** (google): Search for 'northern lights' then switch to the Images tab.
- **stackoverflow_sort_votes** (stackoverflow): Sort questions by votes (highest score).
- **bbc_cookie_then_news** (bbc): Dismiss any cookie banner, then navigate to BBC News.
- **reddit_cookie_then_popular** (reddit): Dismiss any cookie/consent prompts and navigate to the Popular feed.
- **example_com_click_link** (example): Click the 'More information...' link.
- **hackernews_open_first** (news): Open the first story link on the page.
- **wikipedia_main_featured** (en): Click the link to today's featured article.

Artifacts: `docs/benchmarks/2026-03-11-actionset-compare.md` and `docs/benchmarks/2026-03-11-actionset-compare.json`
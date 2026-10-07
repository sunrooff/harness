# Results per question

Supports [ADR-004](../ADR-004-embedding-retrieval.md). One run per setup, 06.10.2026, `gpt-4.1-mini`, k = 5.
Raw data: [official](results-official.json), [custom](results-custom.json), [custom-tuned](results-custom-tuned.json).

- **raw** — rank of the right object when the question goes straight to the search tool (no LLM).
- **agent** — what `retrieval-agent` did; score 1 / 0.5 / 0.

| # | raw MiniLM | raw nomic | official (MiniLM) | custom (nomic) | custom-tuned (nomic) |
|---|---|---|---|---|---|
| Q1 exact | 1 | 1 | found, 1 | Cypher, wrong key → "not found", 0 | found, 1 |
| Q2 exact | 1 | 1 | found, 1 | Cypher, lucky `LIMIT 1`, 1 | found, 1 |
| Q3 exact | 1 | 1 | no search, asked k8s-agent (forbidden), 0.5 | Cypher, 1 | found, 1 |
| Q4 exact | 1 | 1 | found, 1 | Cypher, wrong name → "not found", 0 | found, 1 |
| Q5 paraphrase | 1 | 1 | found, 1 | Cypher ×2, then vector, 1 | found, 1 |
| Q6 paraphrase | 1 | 2 | no search, guessed, 0 | no search, guessed, 0 | no search, guessed, 0 |
| Q7 paraphrase | 1 | 1 | found, 1 | Cypher `CONTAINS 'gateway'`, 1 | found, 1 |
| Q8 paraphrase | 3 | 3 | found at 4, 1 | Cypher ×3, then vector, 1 | found at 3, 1 |
| Q9 paraphrase | 1 | 1 | found, 1 | Cypher ×5, never vector → "not found", 0 | found, 1 |
| Q10 absent | – | – | "not found", 1 | "not found", 1 | "not found", 1 |
| **Total** | 8/9 at 1st | 7/9 at 1st | **8.5** | **6** | **9** |

"found" = the agent searched the vector store and the right object was 1st unless a rank is given.
Q5/Q8 ranks in the custom run were recovered from kagent's session history (the script's parser missed the
custom server's `{"output": {"body": …}}` wrapper at run time; fixed since).

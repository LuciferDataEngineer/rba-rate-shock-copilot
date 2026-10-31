# Search benchmark

Cost: **$0**. Numpy, Postgres with pgvector, and DuckDB with the VSS extension all ran on this machine. No Pinecone, no paid embedding API, no cloud warehouse.

The copilot itself has **2,095** document chunks (384-dimensional MiniLM vectors). That is too small to tell the engines apart, so the timed index repeats those real vectors with a little noise until there are **8,000** vectors. Twenty-five of those vectors are used as queries. Recall is against exact nearest neighbours.

Each engine was timed on the same 25 queries. Numpy multiplies all 25 against the matrix in one call. Postgres and DuckDB run 25 separate statements, so their times include that round-trip.

| Engine | Index build | 25 queries, p50 | Recall@10 vs exact |
| --- | ---: | ---: | ---: |
| Numpy, exact | none | 0.9 ms | 1.00 |
| pgvector HNSW (cosine) | 4.1 s | 19.7 ms | 1.00 |
| DuckDB VSS HNSW (cosine) | 4.6 s | 47.6 ms | 1.00 |

At this size the exact multiply is the fastest way to answer a batch of queries, and both HNSW indexes returned the same neighbours as the exact search. The reason to keep pgvector is not raw speed on 2,000 paragraphs. It is that the same Postgres database holds the full-text index and the vector index, which is what the hybrid search uses. DuckDB remains the warehouse for the rates, prices and repayment marts.

The queries are points that already sit in the index, so this is an easier recall test than a set of brand-new questions. It is still a real comparison of the three local engines on the embeddings this project actually builds. The script is `python -m rba_copilot.benchmark`. The raw numbers are in `reports/benchmark.json`.

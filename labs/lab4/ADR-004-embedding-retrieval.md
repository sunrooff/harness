# ADR-004: Agentic Retrieval — custom qdrant-mcp (nomic) vs official mcp-server-qdrant (MiniLM)

- **Status:** Proposed
- **Date:** 2026-10-06
- **Course:** fwdays — Harness Engineering, Lab 4
- **Repo:** [sunrooff/harness-abox](https://github.com/sunrooff/harness-abox) (fork of [den-vasyliev/abox](https://github.com/den-vasyliev/abox))
- **Branch:** [`feat/llmd-embeddings`](https://github.com/sunrooff/harness-abox/tree/feat/llmd-embeddings), run in GitHub Codespaces

> **Result:** the two embedding models find the right object almost equally well. The agent's score depends on its
> prompt: one rule ("search vectors first") raised the custom setup from 6/10 to 9/10.

## Task

Compare the retrieval quality of `retrieval-agent` with two MCP servers for Qdrant (vector database).

| | Custom (nomic) | Official (MiniLM) |
|---|---|---|
| MCP server | `qdrant-mcp` | `mcp-server-qdrant` (deployed as `qdrant-mcp-official`) |
| Embeddings | llama.cpp, a separate shared service | fastembed, inside the MCP pod |
| Model, dimensions | `nomic-embed-text-v1.5`, 768 | `all-MiniLM-L6-v2`, 384 |
| Search output | hits with scores | hits without scores |
| Memory limit | 256Mi + llama.cpp 1Gi (shared) | 2Gi (crashed with 256Mi) |

## Workflow

1. Paused Flux, so it does not undo our changes to `retrieval-agent`.
2. Saved the OpenAI key in the kagent UI, pointed the model at it and restarted the agents:
   ```bash
   kubectl -n kagent patch modelconfig default-model-config --type=merge -p '{"spec":{"apiKeySecret":"default-model-config"}}'
   kubectl -n kagent rollout restart deploy/k8s-agent deploy/retrieval-agent
   ```
3. Added the official server, search limit 5 like the custom one: [manifests/qdrant-mcp-official.yaml](manifests/qdrant-mcp-official.yaml)
4. Switched `retrieval-agent` between the two servers with `kubectl apply`:
   [official](manifests/retrieval-agent.official.yaml) (own prompt: [prompts/](prompts/retrieval-agent.official.md), no neo4j) /
   [custom](manifests/retrieval-agent.custom.yaml) (abox as is)
5. Indexed the same 23 objects (kagent CRs + HelmReleases) through the agent, one collection per server:
   - same 3 messages in both modes, one chat each: *"Ingest these objects: all kagent.dev Agent objects in namespace
     kagent. List them first. Then work strictly one object at a time … Never call tools in parallel."*, then the same
     for ModelConfig / MCPServer / RemoteMCPServer, then for all HelmReleases;
   - one message for everything failed: parallel writes hit a `409` race, parallel reads hit the OpenAI limit (`429`)

   ![Qdrant: abox-minilm (384d) and abox-nomic (768d), 23 points each](screenshots/qdrant-collections.png)
6. Asked 10 fixed questions ([eval/golden-set.md](eval/golden-set.md)) with [eval/run_eval.py](eval/run_eval.py), in two ways:
   - **raw** — straight to the search tool, no LLM;
   - **agent** — to `retrieval-agent`, new session each.
7. Third run, **custom-tuned**: the custom prompt with one rule changed to "search vectors first, then the graph":
   [manifests/retrieval-agent.custom-tuned.yaml](manifests/retrieval-agent.custom-tuned.yaml)

## Results

| | official (MiniLM) | custom (nomic) | custom-tuned (nomic) |
|---|---|---|---|
| raw: right object 1st (Q1–Q9) | **8/9** | 7/9 | 7/9 |
| agent score (Q1–Q10) | 8.5 | 6 | **9** |
| agent used vector search | 8/10 | 2/10 | 9/10 |
| tool calls per question | **0.9** | 2.7 | 1.1 |
| median latency | 2.7 s | 3.5 s | **2.4 s** |
| model load | every MCP session (12 s cold) | once, in llama.cpp | once, in llama.cpp |

Per question: [eval/results.md](eval/results.md). Tokens and money were not measured. Memory figures are limits, not usage.

## Findings

| Area | Finding | Evidence |
|---|---|---|
| Quality | The embedding models are close | raw search differs in one question (Q6) |
| Quality | The prompt decides the agent score | the custom prompt sends questions to the graph first; bad Cypher missed Q1, Q4, Q9; one rule changed: 6 → 9 |
| Quality | Skipping the search still fails | Q6 failed in every run: the agent answered without a tool call |
| Cost | The official server is heavier to run | model reload per MCP session, 2Gi per pod, a `409` race on the first write |
| Risk | Secrets leak through indexing | the official run stored the neo4j password in the vector store (redacted in the export) |

## Decision

Keep the custom server (**nomic** via llama.cpp) and change the prompt rule to **"vector_find first, the graph for relationships"**:
- quality is the same: 9 vs 8.5 is too small a gap to call either model better;
- custom is lighter by design: the model loads once and is shared;
- the prompt rule gave the biggest gain (+3 answers) for free.

Also: reject answers given without a tool call, and tell indexing prompts to drop secrets.

**Limitations:** one run per setup, 10 questions, small corpus (one answer = 10 %); prompts and stored texts differ
between modes, so the raw row is the closest to a model-only comparison; no questions about relationships.

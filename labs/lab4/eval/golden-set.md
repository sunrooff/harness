# Golden set

Same 10 questions for every setup, each in a new session. Answers taken from the manifests, not from the stored data.

- **exact** — the question contains the literal value (image, URL, version);
- **paraphrase** — same meaning, other words than the manifest; this is where embeddings differ;
- **absent** — not in the data; the right answer is "not found".

| # | Type | Question | Reference | Source |
|---|---|---|---|---|
| Q1 | exact | Which model and provider does default-model-config use? | OpenAI `gpt-4.1-mini` | ModelConfig/default-model-config |
| Q2 | exact | Which container image runs the neo4j MCP server? | `neo4j/mcp:v1.6.0` | MCPServer/neo4j-mcp |
| Q3 | exact | What version of the qdrant Helm chart is deployed? | `1.19.1` | HelmRelease/qdrant |
| Q4 | exact | What is the URL of the kagent tool server? | `http://kagent-tools.kagent:8084/mcp` | RemoteMCPServer/kagent-tool-server |
| Q5 | paraphrase | Which agent can help me move my Deployments to canary or blue-green releases? | `argo-rollouts-conversion-agent` | Agent |
| Q6 | paraphrase | I need to write a query over my Prometheus metrics. Which agent should I ask? | `promql-agent` | Agent |
| Q7 | paraphrase | Which agent knows about Envoy-based API gateways and HTTP routing? | `kgateway-agent` | Agent |
| Q8 | paraphrase | Where does the custom vector memory server get its embeddings from, and which collection does it write to? | `http://llama-cpp-embeddings.llama-cpp:8090`, `abox-nomic` | MCPServer/qdrant-mcp |
| Q9 | paraphrase | Which component serves the nomic text embedding model through llm-d, and from which chart? | `llm-d-embedding`, chart `llm-d-modelservice` v0.3.17 | HelmRelease/llm-d-embedding |
| Q10 | absent | Which agent uses the Anthropic Claude model? | none | — |

Score: 1 = correct, from the store; 0.5 = right object but incomplete, or correct but not from the store
(e.g. delegated to k8s-agent, which the prompt forbids during retrieval); 0 = wrong, or "not found" when it is there.

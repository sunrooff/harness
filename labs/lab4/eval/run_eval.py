#!/usr/bin/env python3
"""Lab 4 eval: ask retrieval-agent the golden set and search each MCP server directly.

Run inside the codespace (needs kubectl; stdlib only):

    python3 run_eval.py official      # retrieval-agent on qdrant-mcp-official (MiniLM)
    python3 run_eval.py custom        # retrieval-agent on qdrant-mcp (nomic)
    python3 run_eval.py custom tuned  # same, with a label: writes results-custom-tuned.json

Two measurements per question:
- agentic: the question goes to retrieval-agent over A2A, in a new session. We record the answer,
  latency, every search call it made and the rank of the source object in each search result.
- raw: the question text goes straight to the MCP server's search tool, no LLM. Shows what the
  embedding model alone ranks first.

Writes results-<mode>[-<label>].json next to this file and prints a summary table.
"""
import json
import re
import subprocess
import sys
import time
import urllib.request
import uuid
from pathlib import Path

MODES = {
    "official": {"svc": "qdrant-mcp-official", "find": "qdrant-find", "collection": "abox-minilm"},
    "custom": {"svc": "qdrant-mcp", "find": "vector_find", "collection": "abox-nomic"},
}

# Mirrors golden-set.md. source = (kind, name) of the object that holds the answer.
GOLDEN = [
    ("Q1", "exact", "Which model and provider does default-model-config use?", ("ModelConfig", "default-model-config")),
    ("Q2", "exact", "Which container image runs the neo4j MCP server?", ("MCPServer", "neo4j-mcp")),
    ("Q3", "exact", "What version of the qdrant Helm chart is deployed?", ("HelmRelease", "qdrant")),
    ("Q4", "exact", "What is the URL of the kagent tool server?", ("RemoteMCPServer", "kagent-tool-server")),
    ("Q5", "paraphrase", "Which agent can help me move my Deployments to canary or blue-green releases?", ("Agent", "argo-rollouts-conversion-agent")),
    ("Q6", "paraphrase", "I need to write a query over my Prometheus metrics. Which agent should I ask?", ("Agent", "promql-agent")),
    ("Q7", "paraphrase", "Which agent knows about Envoy-based API gateways and HTTP routing?", ("Agent", "kgateway-agent")),
    ("Q8", "paraphrase", "Where does the custom vector memory server get its embeddings from, and which collection does it write to?", ("MCPServer", "qdrant-mcp")),
    ("Q9", "paraphrase", "Which component serves the nomic text embedding model through llm-d, and from which chart?", ("HelmRelease", "llm-d-embedding")),
    ("Q10", "absent", "Which agent uses the Anthropic Claude model?", None),
]

A2A_PORT, MCP_PORT = 18083, 18300
A2A_URL = f"http://localhost:{A2A_PORT}/api/a2a/kagent/retrieval-agent/"
MCP_URL = f"http://localhost:{MCP_PORT}/mcp"


def port_forward(target, local, remote):
    p = subprocess.Popen(["kubectl", "-n", "kagent", "port-forward", target, f"{local}:{remote}"],
                         stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    time.sleep(4)
    return p


def post(url, body, headers=None, timeout=300):
    req = urllib.request.Request(url, data=json.dumps(body).encode(), method="POST",
                                 headers={"Content-Type": "application/json", **(headers or {})})
    with urllib.request.urlopen(req, timeout=timeout) as r:
        return r.headers, r.read().decode()


def hits(output):
    """Ordered (kind, name) list from a search tool's text output, either server's format."""
    found = []
    try:
        data = json.loads(output)
    except (json.JSONDecodeError, TypeError):
        data = None
    # official: a JSON list of strings, "<entry><content>…</content><metadata>{json}</metadata></entry>"
    if isinstance(data, list) and all(isinstance(x, str) for x in data):
        output, data = "\n".join(data), None
    for m in re.findall(r"<metadata>(.*?)</metadata>", output or "", re.S):
        try:
            md = json.loads(m)
            found.append((md.get("kind"), md.get("name")))
        except json.JSONDecodeError:
            pass
    if found:
        return found
    # custom: [{"score": .., "payload": {"document": .., "kind": .., "name": ..}}]
    for h in data if isinstance(data, list) else []:
        if isinstance(h, dict):
            p = h.get("payload", {})
            md = p.get("metadata") if isinstance(p.get("metadata"), dict) else p
            found.append((md.get("kind"), md.get("name")))
    return found


def rank(found, source):
    if source is None:
        return None
    names = [n for _, n in found]
    return names.index(source[1]) + 1 if source[1] in names else None


def ask_agent(question):
    body = {"jsonrpc": "2.0", "id": "1", "method": "message/send",
            "params": {"message": {"role": "user", "kind": "message", "messageId": str(uuid.uuid4()),
                                   "parts": [{"kind": "text", "text": question}]}}}
    t0 = time.time()
    _, raw = post(A2A_URL, body)
    latency = round(time.time() - t0, 1)
    res = json.loads(raw).get("result", {})
    calls, responses = [], {}
    for msg in res.get("history", []):
        for part in msg.get("parts", []):
            if part.get("kind") != "data":
                continue
            kind, data = (part.get("metadata") or {}).get("adk_type"), part.get("data", {})
            if kind == "function_call":
                calls.append({"id": data.get("id"), "tool": data.get("name"), "args": data.get("args")})
            elif kind == "function_response":
                out = (data.get("response") or {}).get("output") or json.dumps(data.get("response"))
                # custom qdrant-mcp wraps its result as {"output": {"body": "<json>"}}
                if isinstance(out, dict) and isinstance(out.get("body"), str):
                    out = out["body"]
                responses[data.get("id")] = out if isinstance(out, str) else json.dumps(out)
    for c in calls:
        c["hits"] = hits(responses.get(c["id"], ""))
    answer = "\n".join(p.get("text", "") for a in res.get("artifacts", []) for p in a.get("parts", []))
    return {"latency_s": latency, "state": res.get("status", {}).get("state"), "calls": calls, "answer": answer}


def mcp_search(find_tool, query):
    """Call the search tool directly over MCP streamable HTTP (one session per query)."""
    accept = {"Accept": "application/json, text/event-stream"}

    def rpc(body, sid=None):
        h, raw = post(MCP_URL, body, {**accept, **({"Mcp-Session-Id": sid} if sid else {})}, timeout=120)
        datas = [l[5:].strip() for l in raw.splitlines() if l.startswith("data:")]
        return h, json.loads(datas[-1]) if datas else (json.loads(raw) if raw.strip() else {})

    h, _ = rpc({"jsonrpc": "2.0", "id": 1, "method": "initialize",
                "params": {"protocolVersion": "2025-03-26", "capabilities": {},
                           "clientInfo": {"name": "lab4-eval", "version": "1"}}})
    sid = h.get("Mcp-Session-Id")
    rpc({"jsonrpc": "2.0", "method": "notifications/initialized"}, sid)
    _, r = rpc({"jsonrpc": "2.0", "id": 2, "method": "tools/call",
                "params": {"name": find_tool, "arguments": {"query": query}}}, sid)
    text = "\n".join(c.get("text", "") for c in r.get("result", {}).get("content", []))
    return hits(text)


def main():
    mode = sys.argv[1] if len(sys.argv) > 1 else ""
    if mode not in MODES:
        sys.exit(f"usage: {sys.argv[0]} {'|'.join(MODES)} [label]")
    label = f"-{sys.argv[2]}" if len(sys.argv) > 2 else ""
    cfg = MODES[mode]
    pfs = [port_forward("svc/kagent-controller", A2A_PORT, 8083), port_forward(f"svc/{cfg['svc']}", MCP_PORT, 3000)]
    results = []
    try:
        for qid, qtype, question, source in GOLDEN:
            print(f"{qid} … ", end="", flush=True)
            raw = mcp_search(cfg["find"], question)
            agent = ask_agent(question)
            searches = [c for c in agent["calls"] if c["tool"] == cfg["find"]]
            ranks = [rank(c["hits"], source) for c in searches]
            results.append({
                "id": qid, "type": qtype, "question": question,
                "source": "/".join(source) if source else None,
                "raw_top5": ["/".join(map(str, h)) for h in raw[:5]],
                "raw_rank": rank(raw, source),
                "agent_searches": len(searches),
                "agent_queries": [c["args"].get("query") for c in searches],
                "agent_best_rank": min([r for r in ranks if r], default=None),
                "other_tool_calls": [c["tool"] for c in agent["calls"] if c["tool"] != cfg["find"]],
                **agent,
            })
            print(f"{agent['latency_s']}s, {len(searches)} search(es)")
            time.sleep(10)  # stay under the 200k TPM org limit
    finally:
        for p in pfs:
            p.terminate()

    out = Path(__file__).with_name(f"results-{mode}{label}.json")
    out.write_text(json.dumps({"mode": mode + label, "collection": cfg["collection"], "results": results},
                              indent=2, ensure_ascii=False))
    print(f"\nwrote {out}\n")
    print("| # | type | raw rank | agent best rank | searches | latency s | answer |")
    print("|---|---|---|---|---|---|---|")
    for r in results:
        ans = r["answer"].replace("\n", " ")[:90]
        print(f"| {r['id']} | {r['type']} | {r['raw_rank'] or '–'} | {r['agent_best_rank'] or '–'} "
              f"| {r['agent_searches']} | {r['latency_s']} | {ans} |")


if __name__ == "__main__":
    main()

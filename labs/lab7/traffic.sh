#!/bin/bash
# Lab 7 traffic: same backends see the same spans. Prints only short answers.
kubectl -n otel-demo port-forward svc/agent 18010:8010 >/dev/null 2>&1 & PIDS="$!"
kubectl -n kagent port-forward svc/kagent-controller 18083:8083 >/dev/null 2>&1 & PIDS="$PIDS $!"
trap 'kill $PIDS 2>/dev/null' EXIT
sleep 5
shop() { echo "[shop] $1"; curl -s -m 180 -X POST localhost:18010/prompt -H "Content-Type: application/json" -d "$(jq -n --arg m "$1" '{message:$m}')" | jq -r '.response.messages[-1].content // .detail // "?"' | tr '\n' ' ' | cut -c1-200; echo; sleep 8; }
a2a() { # agent, text, contextId(optional)
  local body; body=$(jq -n --arg t "$2" --arg c "$3" --arg id "lab7-$(date +%s%N)" '{jsonrpc:"2.0",id:"1",method:"message/send",params:{message:({role:"user",kind:"message",messageId:$id,parts:[{kind:"text",text:$t}]} + (if $c=="" then {} else {contextId:$c} end))}}')
  curl -s -m 400 -X POST "localhost:18083/api/a2a/kagent/$1/" -H "Content-Type: application/json" -d "$body" > /tmp/a2a.json
  echo "[$1] $2"; jq -r '.error // empty' /tmp/a2a.json; jq -r '[.result.artifacts[]?.parts[]?.text] | join(" ") | .[0:200]' /tmp/a2a.json; sleep 10; }

shop "Which telescopes do you sell under 500 dollars? Give two names."
shop "What is the cheapest product in the catalog and what does it cost?"
shop "Recommend a product for observing the Moon and explain why in one sentence."
shop "Do you have any products related to solar observation?"
shop "Compare the two most expensive telescopes you sell."

a2a k8s-agent "How many pods are running in namespace lab7? List their names."
ctx=$(jq -r '.result.contextId' /tmp/a2a.json)
a2a k8s-agent "And which container images do they use?" "$ctx"
a2a k8s-agent "Which deployments in namespace otel-demo have fewer ready replicas than desired?"

a2a retrieval-agent "Ingest these objects: all kagent.dev Agent objects in namespace kagent. List them first. Then work strictly one object at a time: fetch it by name, store it, and only then move to the next. Never call tools in parallel."
a2a retrieval-agent "Which agent can help me move my Deployments to canary or blue-green releases?"
a2a retrieval-agent "Which agent knows about Envoy-based API gateways and HTTP routing?"
a2a retrieval-agent "Which agents use the default-model-config model config?"
echo DONE

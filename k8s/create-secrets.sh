#!/usr/bin/env bash
# k8s Secret 생성 스크립트 — 이 파일은 git에 커밋하지 않음
# 사용: bash k8s/create-secrets.sh
set -euo pipefail

NS=devops-pipeline

kubectl create secret generic pipeline-secrets \
  --namespace="${NS}" \
  --from-literal=TELEGRAM_TOKEN="${TELEGRAM_TOKEN:?필수}" \
  --from-literal=TELEGRAM_CHAT_ID="${TELEGRAM_CHAT_ID:?필수}" \
  --from-literal=CLAUDE_API_KEY="${CLAUDE_API_KEY:-}" \
  --from-literal=NOTION_TOKEN="${NOTION_TOKEN:-}" \
  --from-literal=NOTION_PARENT_PAGE_ID="${NOTION_PARENT_PAGE_ID:-}" \
  --from-literal=BRAVE_API_KEY="${BRAVE_API_KEY:-}" \
  --from-literal=HUGGING_FACE_HUB_TOKEN="${HUGGING_FACE_HUB_TOKEN:-}" \
  --dry-run=client -o yaml | kubectl apply -f -

echo "✅ Secret 생성/업데이트 완료"

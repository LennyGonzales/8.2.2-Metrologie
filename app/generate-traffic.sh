#!/usr/bin/env bash
set -euo pipefail

BASE_URL="${1:-http://localhost:8000}"

echo "Start"

for i in $(seq 1 20); do curl -s -o /dev/null "$BASE_URL/ok"; done
for i in $(seq 1 5); do curl -s -o /dev/null "$BASE_URL/bad-request"; done
for i in $(seq 1 3); do curl -s -o /dev/null "$BASE_URL/not-found"; done
for i in $(seq 1 10); do curl -s -o /dev/null "$BASE_URL/error"; done
for i in $(seq 1 5); do curl -s -o /dev/null "$BASE_URL/crash"; done
for i in $(seq 1 3); do curl -s -o /dev/null "$BASE_URL/slow"; done
for i in $(seq 1 5); do curl -s -X POST -o /dev/null "$BASE_URL/trigger-slow"; done

echo "Done"

#!/usr/bin/env bash
set -e
for f in "$(dirname "$0")"/test_*.py; do python3 "$f"; done

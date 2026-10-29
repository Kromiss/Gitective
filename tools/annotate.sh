#!/usr/bin/env bash
# CI helper: run a command; on failure, print its output and repeat the useful part as a
# GitHub annotation (the failing tests, else the last lines), readable without the logs.
# Usage: tools/annotate.sh "Title" command args...
title=$1; shift
log=$(mktemp)
"$@" > "$log" 2>&1 && { cat "$log"; exit 0; }
cat "$log"
part=$(grep -A25 -E '^(FAIL|ERROR):' "$log" || tail -60 "$log")
echo "::error title=$title::$(printf '%s' "$part" | head -150 | sed ':a;N;$!ba;s/%/%25/g;s/\r//g;s/\n/%0A/g')"
exit 1

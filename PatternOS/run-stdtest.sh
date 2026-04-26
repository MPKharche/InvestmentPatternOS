#!/usr/bin/env bash
# Entry point from repo root — forwards to stdtest/run.sh
exec "$(cd "$(dirname "$0")" && pwd)/stdtest/run.sh" "$@"

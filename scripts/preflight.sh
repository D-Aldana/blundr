#!/usr/bin/env bash
# Checks the three toolchains a native setup needs, and says what to install
# for anything missing rather than failing later inside the pipeline.
set -u

MIN_PYTHON=3.10
MIN_NODE=20
missing=0

case "$(uname -s)" in
  Darwin) install_stockfish="brew install stockfish" ;;
  *)      install_stockfish="sudo apt install stockfish" ;;
esac

ok()   { printf '  \033[32m✓\033[0m %s\n' "$1"; }
fail() { printf '  \033[31m✗\033[0m %s\n      %s\n' "$1" "$2"; missing=1; }

# Returns 0 when $1 >= $2, comparing dotted version numbers.
at_least() {
  [ "$(printf '%s\n%s\n' "$2" "$1" | sort -t. -k1,1n -k2,2n | head -1)" = "$2" ]
}

if command -v python3 >/dev/null 2>&1; then
  v=$(python3 -c 'import sys; print("%d.%d" % sys.version_info[:2])')
  if at_least "$v" "$MIN_PYTHON"; then
    ok "python $v"
  else
    fail "python $v is too old" "needs $MIN_PYTHON or newer"
  fi
else
  fail "python3 not found" "install Python $MIN_PYTHON or newer"
fi

if command -v node >/dev/null 2>&1; then
  v=$(node -v | tr -d 'v')
  if at_least "$v" "$MIN_NODE"; then
    ok "node v$v"
  else
    fail "node v$v is too old" "needs v$MIN_NODE or newer"
  fi
else
  fail "node not found" "install Node $MIN_NODE or newer"
fi

engine=${STOCKFISH_PATH:-stockfish}
if command -v "$engine" >/dev/null 2>&1; then
  ok "stockfish ($(command -v "$engine"))"
else
  fail "stockfish not found" "$install_stockfish"
fi

if [ "$missing" -eq 0 ]; then
  echo
  echo "All set. Run 'make dev'."
else
  echo
  echo "Install what's missing above, then run 'make setup' again."
  echo "Or skip local tooling entirely with 'docker compose up'."
fi
exit "$missing"

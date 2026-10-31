#!/usr/bin/env bash
# Fábrica de videos - modo PC (Mac/Linux). Trabaja cada 4 horas mientras la
# computadora esté prendida. Ctrl+C para parar.
set -e
cd "$(dirname "$0")"
if [ ! -d .venv ]; then
  python3 -m venv .venv
  .venv/bin/pip install -q -r requirements.txt
  .venv/bin/pip install -q --no-deps gTTS
fi
[ -f config.toml ] || cp config.example.toml config.toml
[ -f fabrica.toml ] || cp fabrica.example.toml fabrica.toml
exec .venv/bin/python -m fabrica --repetir-cada 4 "$@"

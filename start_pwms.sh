#!/usr/bin/env bash
cd /home/admgelie/Projects/pwms || exit 1
exec /home/admgelie/.local/bin/uv run gunicorn core.wsgi:application --config gunicorn_config.py

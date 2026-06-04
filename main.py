#!/usr/bin/env python
import subprocess


if __name__ == "__main__":
    # subprocess.run(["uv", "run", "manage.py", "runserver", "5000"])
    subprocess.run(["/home/admgelie/.local/bin/uv", "run", "gunicorn", "core.wsgi:application", "--config", "gunicorn_config.py"])

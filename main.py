#!/home/gelie/Projects/pwms/.venv/bin/python
import subprocess


if __name__ == "__main__":
    subprocess.run(["uv", "run", "manage.py", "runserver", "5000"])

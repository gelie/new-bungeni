# gunicorn_config.py
import multiprocessing

# Bind to Unix socket (more secure than TCP) - # requires ROOT access
# bind = "unix:/var/run/gunicorn.sock"
bind = "localhost"

# Number of worker processes
workers = multiprocessing.cpu_count() * 2 + 1

# Worker class (sync is default, good for most cases)
worker_class = "sync"

# Timeout for workers (30 seconds)
timeout = 30

# Access log file
accesslog = "./logs/gunicorn/access.log"
# accesslog = '/var/log/gunicorn/access.log'

# Error log file
errorlog = "./logs/gunicorn/error.log"
# errorlog = '/var/log/gunicorn/error.log'

# Log level
loglevel = "info"

# Daemonize (run in background)
daemon = True

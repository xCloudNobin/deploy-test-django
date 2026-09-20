import multiprocessing
import os

port = os.environ.get("PORT", "8000")
host = os.environ.get("BIND_HOST", "0.0.0.0")
workers = int(os.environ.get("WEB_CONCURRENCY", "2"))

bind = f"{host}:{port}"
accesslog = os.environ.get("GUNICORN_ACCESSLOG", "-")
errorlog = os.environ.get("GUNICORN_ERRORLOG", "-")
proc_name = "taskboard"
timeout = 60
graceful_timeout = 15

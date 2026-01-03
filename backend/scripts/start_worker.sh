
#! /usr/bin/env bash
set -e

# Run Celery Worker
# -A app.celery_app: App instance
# worker: Worker mode
# -l info: Log level
# -c 4: Concurrency (Adjust based on CPU)
# -Q celery: Default queue

# Use 'solo' pool for macOS/AsyncIO compatibility to avoid fork safety issues (CoreFoundation)
celery -A app.celery_app worker -l info -P solo -Q celery


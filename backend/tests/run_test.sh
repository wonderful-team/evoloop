#!/bin/bash
export PYTHONPATH=/Users/huangjinhuan/项目/develop-assistant.cn/evoloop/backend
export SENTRY_DSN="https://example.com/1"
export EVOLOOP_DATABASE_URL="postgresql+asyncpg://postgres:postgres@localhost:5432/evoloop"
export EVOLOOP_REDIS_URL="redis://localhost:6379/0"

/Library/Frameworks/Python.framework/Versions/3.10/bin/python3 test_skill_562_detailed.py

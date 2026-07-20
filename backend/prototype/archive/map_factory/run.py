"""验证编排器。

  uv run python -m prototype.map_factory.run            # 确定性腿(永远跑, 无 LLM/无后端)
  uv run python -m prototype.map_factory.run --agent    # 加 agent 腿(需后端运行 + LLM)
"""
from __future__ import annotations

import argparse

from . import validate_deterministic


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--agent", action="store_true", help="加跑 agent 腿(run_agent_background)")
    args = parser.parse_args()

    rc = validate_deterministic.main()

    if args.agent:
        from . import validate_agent

        print("\n")
        agent_rc = validate_agent.main()
        rc = rc or agent_rc

    return rc


if __name__ == "__main__":
    raise SystemExit(main())

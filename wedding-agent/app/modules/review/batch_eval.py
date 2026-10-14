"""批量验证示例工单；只输出评分／方案，不输出照片地址或原始工单。"""

import argparse
import json
import sys
from pathlib import Path

from app.common.config import settings
from app.common.errors import ModuleError
from app.modules.review import check, retouch


def evaluate_cases(paths: list[Path]) -> tuple[list[dict], bool]:
    if not settings.fake_for("review"):
        raise ModuleError("GENERATION_FAILED", "本轮批量评测仅支持演示模式，真实评测待选型后接入")
    reports = []
    failed = False
    for path in paths:
        try:
            state = json.loads(path.read_text(encoding="utf-8"))
            if not isinstance(state, dict):
                raise ValueError("expected state object")
            result = check(state)
            report = {"case": path.name, "mode": "fake", "result": result}
            if not result["passed"] or state.get("user_feedback"):
                report.update(retouch({**state, **result}))
            reports.append(report)
        except ModuleError as error:
            failed = True
            reports.append({"case": path.name, "mode": "fake", "error": {"code": error.code, "message": error.message}})
        except (OSError, ValueError):
            failed = True
            reports.append({"case": path.name, "mode": "fake", "error": {"code": "FILE_INVALID", "message": "示例工单无法读取或不是有效的 JSON 对象"}})
    return reports, failed


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("cases", nargs="+", type=Path, help="示例工单 JSON，可一次指定多份")
    args = parser.parse_args()
    try:
        reports, failed = evaluate_cases(args.cases)
    except ModuleError as error:
        sys.stderr.write(f"{error.code}: {error.message}\n")
        return 1
    sys.stdout.write(json.dumps(reports, ensure_ascii=False, indent=2) + "\n")
    return int(failed)


if __name__ == "__main__":
    raise SystemExit(main())

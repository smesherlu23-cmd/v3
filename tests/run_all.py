"""Все тесты Centurio без pytest: `python tests/run_all.py`.

Каждая проверка — вызов ok(); упавший тест не останавливает остальные, а
в конце печатается сводка с тем же правилом про пропуски, что и под pytest.
"""
import importlib
import os
import sys
import traceback
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE.parent))
sys.path.insert(0, str(HERE))

import helpers  # noqa: E402


def main() -> int:
    for path in sorted(HERE.glob("test_*.py")):
        module = importlib.import_module(path.stem)
        for name, fn in list(vars(module).items()):
            if not (name.startswith("test_") and callable(fn)):
                continue
            try:
                fn()
            except helpers.CheckFailed as exc:
                print(f"FAIL: {path.stem}.{name}: {exc}")
            except Exception:
                helpers._failed += 1
                print(f"FAIL: {path.stem}.{name} raised")
                traceback.print_exc()
    code, line = helpers._summarize(helpers._passed, helpers._failed, helpers._skipped,
                                    bool(os.environ.get("CI")))
    print(f"\n{line}")
    return code


if __name__ == "__main__":
    sys.exit(main())

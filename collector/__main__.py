"""수집 진입점.

    python -m collector           # 전부 수집
    python -m collector themes    # 테마만
    python -m collector sentiment # 공포·탐욕만
"""

import os
import sys

from . import sentiment, themes

TASKS = {"themes": themes.write, "sentiment": sentiment.write}


def load_dotenv(path: str = ".env") -> None:
    """의존성 없이 .env 를 읽어 환경변수에 넣습니다. 이미 있는 값은 건드리지 않습니다.

    GitHub Actions 는 Secrets 를 환경변수로 직접 주입하므로 .env 가 없어도 됩니다.
    """
    if not os.path.exists(path):
        return
    with open(path, encoding="utf-8") as fh:
        for line in fh:
            line = line.strip()
            if not line or line.startswith("#") or "=" not in line:
                continue
            key, _, value = line.partition("=")
            key, value = key.strip(), value.strip().strip('"').strip("'")
            if key and key not in os.environ:
                os.environ[key] = value


def main() -> int:
    load_dotenv()
    requested = sys.argv[1:] or list(TASKS)
    unknown = [t for t in requested if t not in TASKS]
    if unknown:
        print(f"알 수 없는 작업: {', '.join(unknown)}")
        print(f"가능한 작업: {', '.join(TASKS)}")
        return 2

    failed = []
    for task in requested:
        print(f"\n=== {task} ===")
        try:
            TASKS[task]()
        except Exception as exc:  # noqa: BLE001
            print(f"실패: {exc}")
            failed.append(task)

    if failed:
        print(f"\n{len(failed)}개 작업 실패: {', '.join(failed)}")
        return 1
    print("\n전부 완료")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

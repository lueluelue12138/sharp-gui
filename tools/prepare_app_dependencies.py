"""显式安装/构建入口，只准备当前应用的锁定依赖。"""

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from application_dependencies import DependencyError, load_contract, prepare


def main():
    try:
        lock = load_contract(ROOT)
        if lock is not None:
            prepare(ROOT, lock)
        print('Application dependencies verified / 应用依赖已校验')
        return 0
    except DependencyError as exc:
        print(f'Application dependency error / 应用依赖准备失败: {exc.code}', file=sys.stderr)
        return 1


if __name__ == '__main__':
    raise SystemExit(main())

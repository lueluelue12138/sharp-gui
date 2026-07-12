import os
import sys

from backend.app_factory import create_app
from backend.server import (
    WINDOWS_SERVER_CHILD_ENV,
    run_server,
    run_windows_server_supervisor,
)


if (
    __name__ == "__main__"
    and os.name == "nt"
    and os.environ.get(WINDOWS_SERVER_CHILD_ENV) != "1"
):
    raise SystemExit(run_windows_server_supervisor([
        os.path.abspath(__file__),
        *sys.argv[1:],
    ]))


app = create_app()


if __name__ == "__main__":
    run_server(app)

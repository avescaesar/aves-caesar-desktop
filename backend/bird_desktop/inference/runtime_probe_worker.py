from __future__ import annotations

import sys

from .providers import RuntimeResolver
from ..runtime.config import RuntimeConfig
from ..runtime.worker_io import WorkerLogRedirect


class RuntimeProbeWorker:
    def run(self) -> None:
        with WorkerLogRedirect(sys.argv[1] if len(sys.argv) > 1 else None):
            config = RuntimeConfig.load()
            runtime = RuntimeResolver.resolve(config)

        print(RuntimeResolver.encode(runtime), flush=True)


if __name__ == "__main__":
    RuntimeProbeWorker().run()

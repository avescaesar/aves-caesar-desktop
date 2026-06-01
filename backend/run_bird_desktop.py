from __future__ import annotations

import multiprocessing
import sys

from bird_desktop.collection.worker import CollectionWorker
from bird_desktop.inference.runtime_probe_worker import RuntimeProbeWorker
from bird_desktop.main import main
from bird_desktop.organization.worker import BatchWorker
from bird_desktop.prediction_worker import PredictionWorker
from bird_desktop.runtime.worker_process import WorkerProcessCommand


class FrozenEntrypoint:
    WORKERS = {
        "collection.worker": CollectionWorker,
        "inference.runtime_probe_worker": RuntimeProbeWorker,
        "organization.worker": BatchWorker,
        "prediction_worker": PredictionWorker,
    }


    def run(self) -> None:
        multiprocessing.freeze_support()
        if self._is_worker_process():
            self._run_worker()
            return

        main()


    def _is_worker_process(self) -> bool:
        return len(sys.argv) >= 3 and sys.argv[1] == WorkerProcessCommand.FROZEN_WORKER_ARGUMENT


    def _run_worker(self) -> None:
        worker_name = sys.argv[2]
        worker_class = self.WORKERS.get(worker_name)
        if worker_class is None:
            raise RuntimeError(f"Unknown worker process: {worker_name}")

        sys.argv = [sys.argv[0], *sys.argv[3:]]
        worker_class().run()


if __name__ == "__main__":
    FrozenEntrypoint().run()

from time import time
import datetime

import logging

logger = logging.getLogger(__name__)


class Timer:
    def __init__(self, total_measures: int = 0, measures_completed: int = 0):
        self.measurement_id = None
        self.timestamps = {}
        self.default_key = object()

        self.total_measures = total_measures
        self.already_completed = measures_completed

        self.measured_count = 0
        self.total_processing_time = 0

    def measure(self, uid: str | None = None, measure_count: int = 1):
        if uid is None:
            uid = self.default_key

        self.timestamps[uid] = self.timestamps.get(uid, 0)

        if self.timestamps[uid] == 0:
            self.timestamps[uid] = time()
        else:
            self.total_processing_time += time() - self.timestamps[uid]
            self.measured_count += measure_count
            del self.timestamps[uid]

    def print_status(self, with_progressbar=True, with_time_remaining=False):
        logger.info(f"Finished {self.measured_count + self.already_completed} out of {self.total_measures}.")

        if with_progressbar:
            norm_progress = (self.already_completed + self.measured_count) / self.total_measures

            bar_length = 50
            completed_length = int(bar_length * norm_progress)
            bar = "█" * completed_length + "-" * (bar_length - completed_length)

            percentage = norm_progress * 100
            logger.info(f"[{bar}] {percentage:.2f}% complete")

        if with_time_remaining:
            avg_time_per_measurement = self.total_processing_time / self.measured_count
            remaining_measurements = self.total_measures - self.already_completed - self.measured_count

            logger.info(
                f"Approximately "
                f"{datetime.timedelta(seconds=remaining_measurements * avg_time_per_measurement)} seconds remains"
            )
        print("\n\n")

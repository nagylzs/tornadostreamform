"""Monitor and limit bandwidth for streamed requests."""
import time
import math


def format_any(value, unit):
    fmt = '%6.2f %s%s'
    prefixes = ' kMGTPEZY'
    if value < 2e-10:
        scaled = power = 0
    else:
        power = int(math.log(value, 1000))
        scaled = value / 1000. ** power
    return fmt % (scaled, prefixes[power], unit)


def format_speed(value):
    return format_any(value, "B/sec")


def format_size(value):
    return format_any(value, "B")


class BandwidthMonitor:
    """This class can be used to monitor data transfer speed for a MultiPartStreamer.

    You will most likely create a BandwidthMonitor instance in the prepare() method of your request handler."""

    hist_interval = 0.5  # Minimum number of seconds between two history records.
    hist_max_size = 100  # Max. history size. Zero means infinite.

    def __init__(self, total):
        """Create new bandwidth monitor.

        :param total: Total size of the request in bytes. If you don't know this value then you can use zero,
            but then you can't call the get_remaining_time() method.
        """
        self.started = None  # When the request started
        self.total = total  # Total size of the request in bytes
        self.received = 0  # Bytes received so far
        self.elapsed = None  # Seconds elapsed so far

        self.last_received = None  # Last time we have received data
        self.curr_speed = 0.0  # Current speed, based on the time between last two chunks
        self.avg_speed = 0.0  # Average speed, based on the whole transfer

        self.history = []  # History, containing tuples of (time, total_received) pairs
        self.remaining_time = None  # Estimated remaining time in seconds.

    def get_avg_speed(self, look_back_steps=10):
        """Calculate average speed from the last few seconds.

        :param look_back_steps: Number of steps to go back in history.
        :return: Average speed between now and the looked back point in time.
            This method may use a shorter time if the number of history records is less than look_back_steps.
            This method may return None if the number of history records is less than two."""
        if len(self.history) < 2:
            return None
        start = self.history[-1]
        if len(self.history) > look_back_steps:
            end = self.history[-look_back_steps - 1]
        else:
            end = self.history[0]

        received, elapsed = start[1] - end[1], start[0] - end[0]
        return received / elapsed

    def get_remaining_time(self, speed=None):
        """Calculate the time needed to complete the request.

        :param speed: Use this speed for the calculation. When not given, the last known speed will be used.
        :return: If the current speed is zero or not known, then None is returned. Otherwise the number of seconds
            is returned."""
        if speed is None:
            speed = self.curr_speed
        if speed and speed > 0.1:
            return (self.total - self.received) / speed
        else:
            return None

    def data_received(self, size):
        """Call this when a chunk of data was received.

        :param size: Number of bytes received.

        This will update all statistics.
        """
        assert size > 0
        now = time.time()
        if not self.started:
            self.started = now
        self.received += size
        self.elapsed = now - self.started

        # Calculate current speed.
        if self.last_received:
            elapsed = now - self.last_received
            if elapsed > 0.0:
                self.curr_speed = size / elapsed

        # Calculate average speed
        if self.received > 0 and self.elapsed > 0:
            self.avg_speed = self.received / self.elapsed

        # Update last received time
        self.last_received = now

        # Save history, if needed
        if not self.history or (now - self.history[-1][0] >= self.hist_interval):
            self.history.append((now, self.received))

        # Prune history, if needed.
        if len(self.history) > self.hist_max_size:
            self.history.pop()

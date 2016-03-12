from __future__ import print_function, division, absolute_import

import logging
from timeit import default_timer

from tornado import gen
from tornado.queues import Queue
from tornado.iostream import StreamClosedError

from .core import read, write
from .utils import log_errors


logger = logging.getLogger(__name__)


class BatchedStream(object):
    def __init__(self, stream, interval):
        self.stream = stream
        self.interval = interval / 1000.
        self.last_transmission = default_timer()
        self.send_q = Queue()
        self.recv_q = Queue()
        self._background_send_coroutine = self._background_send()
        self._background_recv_coroutine = self._background_recv()

        self._last_write = None

    @gen.coroutine
    def _background_send(self):
        with log_errors():
            while True:
                msg = yield self.send_q.get()
                msgs = [msg]
                now = default_timer()
                wait_time = now - self.last_transmission + self.interval
                if wait_time > 0:
                    yield gen.sleep(wait_time)
                while not self.send_q.empty():
                    msgs.append(self.send_q.get_nowait())

                self._last_write = write(self.stream, msgs)
                yield self._last_write
                if len(msgs) > 1:
                    logger.debug("Batched messages: %d", len(msgs))
                for _ in msgs:
                    self.send_q.task_done()

    @gen.coroutine
    def _background_recv(self):
        with log_errors():
            while True:
                try:
                    msgs = yield read(self.stream)
                except StreamClosedError:
                    break
                assert isinstance(msgs, list)
                if len(msgs) > 1:
                    # logger.info("Batched messages: %d", len(msgs))
                    print("Batched messages: %d" % len(msgs))
                for msg in msgs:
                    self.recv_q.put_nowait(msg)

    @gen.coroutine
    def flush(self):
        yield self.send_q.join()

    def send(self, msg):
        self.send_q.put_nowait(msg)

    def recv(self):
        return self.recv_q.get()

    @gen.coroutine
    def close(self):
        yield self.flush()
        return self.stream.close()

    def closed(self):
        return self.stream.closed()

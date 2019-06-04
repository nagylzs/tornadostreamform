#!/usr/bin/env python3
import os
import sys

from tornado.httpserver import HTTPServer
from tornado.ioloop import IOLoop
from tornado.web import RequestHandler, Application, url, stream_request_body

sys.path.insert(0, os.pardir)
# noinspection PyPep8
from tornadostreamform.multipart_streamer import MultiPartStreamer, StreamedPart, TemporaryFileStreamedPart
from tornadostreamform.bandwidthmonitor import BandwidthMonitor

"""Important knowledge for Tornado users: nax_buffer_size and max_body_size should be low by default.
The biggest file that can be POST-ed should be specified in the prepare() method of the stream_request_body handler.

For details see: https://groups.google.com/forum/#!topic/python-tornado/izEXQd71rQk
"""
MB = 1024 * 1024
GB = 1024 * MB
TB = 1024 * GB

MAX_BUFFER_SIZE = 4 * MB  # Max. size loaded into memory!
MAX_BODY_SIZE = 4 * MB  # Max. size loaded into memory!
MAX_STREAMED_SIZE = 1 * TB  # Max. size streamed in one request!
TMP_DIR = '/tmp'  # Path for storing streamed temporary files. Set this to a directory that receives the files.

if not os.path.isdir(TMP_DIR):
    raise SystemExit("Please change TMP_DIR to an existing directory.")

class MyRequest(RequestHandler):
    def no_cache(self):
        """Disable caching of this page."""
        self.set_header('Cache-Control', 'no-store, no-cache, must-revalidate, max-age=0')


class MyStreamer(MultiPartStreamer):
    """You can create your own multipart streamer, and override some methods."""

    def __init__(self, total):
        super().__init__(total)
        self._last_progress = 0.0  # Last time of updating the progress
        self.bwm = BandwidthMonitor(total)

    def create_part(self, headers):
        """In the create_part method, you should create and return StreamedPart instance.

        :param headers: A dict of header values for the new part to be created.

        For example, you can write your own StreamedPart descendant that streams data into a process (through a
        pipe) or send it on the network with another tornado.httpclient etc. You just need to make sure that you
        use async I/O operations that are supported by tornado. In this example, we use the default create_part()
        method that creates a TemporaryFileStreamedPart instance.

        If you do not override this method, then a TemporaryFileStreamedPart will be created with system default
        temporary directory."""
        global TMP_DIR
        dummy = StreamedPart(self, headers)  # you can use a dummy StreamedPart to examine the headers.
        print("Starting new part, is_file=%s, headers=%s" % (dummy.is_file(), headers))
        return TemporaryFileStreamedPart(self, headers, tmp_dir=TMP_DIR)

    def data_received(self, chunk):
        super().data_received(chunk)
        self.bwm.data_received(len(chunk))  # Monitor bandwidth changes
        # print(self.bwm.get_remaining_time(self.bwm.get_avg_speed(10)))


class MainHandler(MyRequest):
    """Main handler displays the main page (static)"""

    def get(self):
        self.no_cache()
        self.write(open("02_browser_side_progressbar.html", "r").read())


@stream_request_body
class StreamHandler(RequestHandler):
    def prepare(self):
        """In request preparation, we get the total size of the request and create a MultiPartStreamer for it.

        In the prepare method, we can call the connection.set_max_body_size() method to set the max body size
        that can be **streamed** in the current request. We can do this safely without affecting the general
        max_body_size parameter."""
        global MAX_STREAMED_SIZE
        if self.request.method.lower() == "post":
            self.request.connection.set_max_body_size(MAX_STREAMED_SIZE)

        try:
            total = int(self.request.headers.get("Content-Length", "0"))
        except KeyError:
            total = 0  # For any well formed browser request, Content-Length should have a value.
        # noinspection PyAttributeOutsideInit
        self.ps = MyStreamer(total)

    def data_received(self, chunk):
        """When a chunk of data is received, we forward it to the multipart streamer.

        :param chunk: Binary string received for this request."""
        self.ps.data_received(chunk)

    def post(self):
        """Finally, post() is called when all of the data has arrived.

        Here we can do anything with the parts."""
        print("\n\npost() is called when streaming is over.")
        try:
            # Before using the form parts, you **must** call data_complete(), so that the last part can be finalized.
            self.ps.data_complete()
            # Use self.ps.parts here!
        finally:
            # Don't forget to release temporary files.
            self.ps.release_parts()


def main():
    application = Application([
        url(r"/", MainHandler),
        url(r"/upload", StreamHandler),
    ],
            static_path='static')
    http_server = HTTPServer(
            application,
            max_buffer_size=MAX_BUFFER_SIZE,
            max_body_size=MAX_BODY_SIZE,
    )
    http_server.listen(8888)
    IOLoop.instance().start()


print("""
This second example shows how to create a progress bar on the browser side. In this example, we use javascript code
embedded in a single HTML page.

Point your browser to http://127.0.0.1:8888
""")

main()

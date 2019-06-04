#!/usr/bin/env python3
import os
import sys
import time

from tornado.httpserver import HTTPServer
from tornado.ioloop import IOLoop
from tornado.web import RequestHandler, Application, url, stream_request_body

sys.path.insert(0, os.pardir)
# noinspection PyPep8
from tornadostreamform.multipart_streamer import MultiPartStreamer, StreamedPart, TemporaryFileStreamedPart
from tornadostreamform.bandwidthmonitor import BandwidthMonitor, format_speed, format_size

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


class MyStreamer(MultiPartStreamer):
    """You can create your own multipart streamer, and override some methods."""

    def __init__(self, total):
        super().__init__(total)
        self._last_progress = 0.0  # Last time of updating the progress
        self.bwm = BandwidthMonitor(total)  # Create a bandwidth monitor

    def create_part(self, headers):
        """In the create_part method, you should create and return StreamedPart instance.

        :param headers: A dict of header values for the new part to be created.

        For example, you can write your own StreamedPart descendant that streams data into a process (through a
        pipe) or send it on the network with another tornado.httpclient etc. You just need to make sure that you
        use async I/O operations that are supported by tornado. If you do not override this method,
        then the default create_part() method that creates a TemporaryFileStreamedPart instance for you. and it
        will stream file data into the system default temporary directory.
        """
        global TMP_DIR

        # you can use a dummy StreamedPart to examine the headers, as shown below.
        dummy = StreamedPart(self, headers)
        print("Starting new part, is_file=%s, headers=%s" % (dummy.is_file(), headers))

        # This is how you create a streamed file in a given directory.
        return TemporaryFileStreamedPart(self, headers, tmp_dir=TMP_DIR)

        # The default method creates a TemporaryFileStreamedPart with default tmp_dir.
        # return super().create_part(headers)

    def data_received(self, chunk):
        """This method is called when data has arrived for the form.

        :param chunk: Binary string, data chunk received from the client.

        The default implementation does incremental parsing of the data, calls create_part for each part
        in the multipart/form-data and feeds data into the parts.

        In this example, we also monitor the upload speed / bandwidth for the upload."""
        super().data_received(chunk)
        self.bwm.data_received(len(chunk))  # Monitor bandwidth changes

    def on_progress(self, received, total):
        """The on_progress method is called when data is received but **before** it is fed into the current part.

        :param received: Number of bytes received
        :param total: Total bytes to be received.

        For the demonstration, we calculate the progress percent and remaining time of the upload, and display it.
        """
        if self.total:
            now = time.time()
            if now - self._last_progress > 0.5:
                self._last_progress = now

                percent = round(received * 1000 // total) / 10.0
                # Calculate average speed from the last 10*self.bwm.hist_interval = 5 seconds.
                speed = self.bwm.get_avg_speed(look_back_steps=10)
                if speed:
                    s_speed = format_speed(speed)
                    remaining_time = self.bwm.get_remaining_time(speed)
                    if remaining_time is not None:
                        mins = int(remaining_time / 60)
                        secs = int(remaining_time - mins * 60)
                        s_remaining = "%s:%s" % (
                            str(mins).rjust(2, '0'),
                            str(secs).rjust(2, '0'),
                        )
                    else:
                        s_remaining = "?"
                else:
                    s_speed = "?"
                    s_remaining = "?"
                sys.stdout.write("  %.1f%% speed=%s remaining time=%s\n" % (percent, s_speed, s_remaining))
                sys.stdout.flush()

    def examine(self):
        """Debug method: print the structure of the multipart form to stdout."""
        for part in self.parts:
            print("PART name=%s, filename=%s, size=%s" % (part.get_name(), part.get_filename(), part.get_size()))
            for hdr in part.headers:
                print("\tHEADER name=%s" % hdr.get("name", "???"))
                for key in sorted(hdr.keys()):
                    if key.lower() != "name":
                        print("\t\t\t%s=%s" % (key, hdr[key]))


#
# In order to use the stream parser, you need to use the stream_request_body decorator on you RequestHandler.
#
@stream_request_body
class StreamHandler(RequestHandler):
    def get(self):
        self.write('''<html><body>
<form method="POST" action="/" enctype="multipart/form-data">
File #1: <input name="file1" type="file"><br>
File #2: <input name="file2" type="file"><br>
File #3: <input name="file3" type="file"><br>
Other field 1: <input name="other1" type="text"><br>
Other field 2: <input name="other2" type="text"><br>
Other field 3: <input name="other3" type="text"><br>
<input type="submit">
</form>
</body></html>''')

    def prepare(self):
        """In request preparation, we get the total size of the request and create a MultiPartStreamer for it.

        In the prepare method, we can call the connection.set_max_body_size() method to set the max body size
        that can be **streamed** in the current request. We can do this safely without affecting the general
        max_body_size parameter."""
        global MAX_STREAMED_SIZE
        if self.request.method.lower() == "post":
            self.request.connection.set_max_body_size(MAX_STREAMED_SIZE)
            print("Changed max streamed size to %s" % format_size(MAX_STREAMED_SIZE))

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
            # Use parts here!
            self.set_header("Content-Type", "text/plain")
            out = sys.stdout
            try:
                sys.stdout = self
                self.ps.examine()
            finally:
                sys.stdout = out
        finally:
            # Don't forget to release temporary files.
            self.ps.release_parts()


def main():
    application = Application([
        url(r"/", StreamHandler),
    ])
    http_server = HTTPServer(
            application,
            max_body_size=MAX_BODY_SIZE,
            max_buffer_size=MAX_BUFFER_SIZE,
    )
    http_server.listen(8888)
    IOLoop.instance().start()


print("""
This is the simplest example that demonstrates the usage of the multipart_streamer.MultiPartStreamer class.
In this example, we do not have anything on the browser side except a simple html form that can post files to
the server.

After starting this server, point your browser to http://127.0.0.1:8888 and select some large files into
the file inputs. Also give some values in the non-file inputs, and submit the form.

Here on the server side, should see the percentage increasing. When the upload completes, the server sends back
the structure of the uploaded form to the browser and it is displayed.
""")

main()

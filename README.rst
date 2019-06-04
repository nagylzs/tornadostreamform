
tornadostreamform
=================

Pure python module that let's you upload **huge** files to a tornado
web server.

This project provides the ``tornadostreamform.multipart_streamer.MultiPartStreamer``
class that incrementally parses incoming multipart/form-data, splits it into form fields, and streams the fields
into file like objects (temp file, opened pipe, network socket etc.) With this class, it is possible to POST/PUT
large files to a tornado server, without loading anything big into memory.

Documentation
-------------

http://pythonhosted.org/tornadostreamform/


Installation
------------

.. code-block:: shell

    pip3 install tornado
    pip3 install tornadostreamform

License
-------

Copyright 2015 Laszlo Zsolt Nagy

Licensed under the Apache License, Version 2.0 (the "License");
you may not use this file except in compliance with the License.
You may obtain a copy of the License at

    http://www.apache.org/licenses/LICENSE-2.0

Unless required by applicable law or agreed to in writing, software
distributed under the License is distributed on an "AS IS" BASIS,
WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
See the License for the specific language governing permissions and
limitations under the License.

Changelog
---------

v1.0.1 - 2019-06-04 - Python 2 compatibility dropped, upgraded to tornado 6.0, moved to GitHub.

v0.1.1 - 2015-11-26 - First public release

v0.1.0 - Initial beta version


Getting Started
---------------

Request handlers that are not decorated with ``stream_request_body`` load the whole request into memory
unconditionally. By the time ``post()`` and ``put()`` methods are called, the whole request was already loaded
into memory. When you create your web server, you should separate "normal" request handlers that accept small number
of arguments/parameters, and request handlers that are used for streaming large files.
You need to make sure that "normal" request handlers cannot be used to attack the server.

Creating a basic policy about request sizes
...........................................

Lower the ``max_buffer_size`` and ``max_body_size`` parameters of your tornado application first:


.. code-block:: python

    from tornado.web import RequestHandler, Application, url, stream_request_body
    from tornado.httpserver import HTTPServer
    from tornado.ioloop import IOLoop
    from tornadostreamform.multipart_streamer import MultiPartStreamer, StreamedPart, TemporaryFileStreamedPart

    MB = 1024 * 1024
    GB = 1024 * MB
    TB = 1024 * GB

    MAX_BUFFER_SIZE = 1 * MB  # Max. size loaded into memory!
    MAX_BODY_SIZE = 1 * MB  # Max. size loaded into memory!

    # ... more code here to create your application

    http_server = HTTPServer(
            application,
            max_body_size=MAX_BODY_SIZE,
            max_buffer_size=MAX_BUFFER_SIZE,
    )
    http_server.listen(8888)
    IOLoop.instance().start()

Create your own streamer
........................

You can use the ``MultipartStreamer`` class as a base class for streaming big requests. By default, it will create a
new temporary file for each field in the multipart/form-data field, but you can override its ``create_part``
method and stream the data into any file-like object (network socket, opened pipe of a running process etc.)

.. code-block:: python

    class MyStreamer(MultiPartStreamer):
        def create_part(self, headers):
            """In the create_part method, you should create and return StreamedPart instance.

            If you do not override this method, then the default create_part() method that creates a
            TemporaryFileStreamedPart instance for you. and it will stream file data into the system default
            temporary directory.
            """
            return TemporaryFileStreamedPart(self, headers, tmp_dir=None)


If you are happy with the default implementation, then you can use ``MultiPartStreamer`` as-is. For the few request
handlers that are going to accept large files, you need to increase the max body size in their prepare method.
Here is how you do it:

.. code-block:: python

    MAX_STREAMED_SIZE = 1*TB # Max. size to be streamed

    @stream_request_body
    class StreamHandler(RequestHandler):
        def prepare(self):
            """Prepare is called after headers become available for the request."""
            global MAX_STREAMED_SIZE
            # If the request is authorized, then you can increase the default max_body_size by this call.
            if self.request.method.lower() == "post":
                self.request.connection.set_max_body_size(MAX_STREAMED_SIZE)
            # You can get the total request size from the headers.
            try:
                total = int(self.request.headers.get("Content-Length", "0"))
            except KeyError:
                total = 0  # For any well formed browser request, Content-Length should have a value.
            # And here you create a streamer that will accept incoming data
            self.ps = MyStreamer(total)

        def data_received(self, chunk):
            """When a chunk of data is received, we forward it to the multipart streamer."""
            self.ps.data_received(chunk)

        def post(self):
            """post() or put() is called when all of the data has already arrived."""
            try:
                self.ps.data_complete() # You MUST call this to close the incoming stream.
                # Here can use self.ps to access the fields and the corresponding ``StreamedPart`` objects.
            finally:
                # When ready, don't forget to release resources.
                self.ps.release_parts()
                self.finish() # And of course, you MUST call finish()

For completeness, here is the application definition:

.. code-block:: python

    application = Application([
        url(r"/", MainPageHandler), # Normal request handler
        url(r"/upload", StreamHandler), Streaming request handler
        # .... more handlers here
    ])


Use the example server for the know-how
.......................................

Use the source code of provided test web server to explore the possibilities with tornadostreamform and Tornado.

.. code-block:: shell

    hg clone https://bitbucket.org/nagylzs/tornadostreamform
    cd tornadostreamform/test
    python3.6 01_multipart_streamer.py # and then point your browser to port :8888
    python3.6 02_multipart_streamer.py # and then point your browser to port :8888

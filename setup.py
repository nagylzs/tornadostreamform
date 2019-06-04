#!/usr/bin/env python
from distutils.core import setup
from tornadostreamform.version import release

setup(name='tornadostreamform',
      version=release,
      description='Stream huge files with Tornado web server',
      long_description="""Provides a simple module that can be used to """
                       """stream huge multipart/form-data requests with """
                       """Tornado web server.""",
      author='László Zsolt Nagy',
      author_email='nagylzs@gmail.com',
      license="http://www.apache.org/licenses/LICENSE-2.0",
      packages=['tornadostreamform'],
      requires=['tornado (>=6.0)'],
      url="https://bitbucket.org/nagylzs/tornadostreamform",
      classifiers=[
          'Topic :: Security', 'Topic :: Internet :: WWW/HTTP',
          "Programming Language :: Python :: 3.6",
          "Programming Language :: Python :: Implementation :: CPython",
      ],
      )

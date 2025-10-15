=======================
django-http-compression
=======================

.. image:: https://img.shields.io/github/actions/workflow/status/adamchainz/django-http-compression/main.yml.svg?branch=main&style=for-the-badge
   :target: https://github.com/adamchainz/django-http-compression/actions?workflow=CI

.. image:: https://img.shields.io/badge/Coverage-100%25-success?style=for-the-badge
  :target: https://github.com/adamchainz/django-http-compression/actions?workflow=CI

.. image:: https://img.shields.io/pypi/v/django-http-compression.svg?style=for-the-badge
  :target: https://pypi.org/project/django-http-compression/

.. image:: https://img.shields.io/badge/code%20style-black-000000.svg?style=for-the-badge
   :target: https://github.com/psf/black

.. image:: https://img.shields.io/badge/pre--commit-enabled-brightgreen?logo=pre-commit&logoColor=white&style=for-the-badge
   :target: https://github.com/pre-commit/pre-commit
   :alt: pre-commit

Django middleware for compressing HTTP responses with Zstandard, Brotli, or Gzip.

For a bit of background, see the `introductory blog post <https://adamj.eu/tech/2025/10/10/introducing-django-http-compression/>`__.

----

**Work smarter and faster** with my book `Boost Your Django DX <https://adamchainz.gumroad.com/l/byddx>`__ which covers many ways to improve your development experience.

----

Requirements
------------

Python 3.9 to 3.14 supported.

Django 4.2 to 6.0 supported.

From Python 3.14, Zstandard support requires `libzstd <https://github.com/facebook/zstd>`__ to be linked into Python.
(uv’s Python distributions include it on Unix.)

Installation
------------

1. Install with **pip**:

   .. code-block:: sh

       python -m pip install django-http-compression

  To include Brotli support, add the ``brotli`` extra to pull in the `brotli <https://pypi.org/project/Brotli/>`__ package:

  .. code-block:: sh

      python -m pip install 'django-http-compression[brotli]'

  Most browsers support Zstandard (`MDN <https://developer.mozilla.org/en-US/docs/Web/HTTP/Reference/Headers/Content-Encoding#browser_compatibility>`__), but you may want to include Brotli as an option for clients that do not.

2. Add django-http-compression to your ``INSTALLED_APPS``:

   .. code-block:: python

       INSTALLED_APPS = [
           ...,
           "django_http_compression",
           ...,
       ]

3. Add the middleware:

   .. code-block:: python

       MIDDLEWARE = [
           ...,
           "django_http_compression.middleware.HttpCompressionMiddleware",
           ...,
       ]

   The middleware should be *above* any that may modify your HTML, such as those of `django-debug-toolbar <https://django-debug-toolbar.readthedocs.io/>`__ or `django-browser-reload <https://pypi.org/project/django-browser-reload/>`__.
   Remove any other middleware that will encode your responses, such as Django’s |GZipMiddleware|__.

   .. |GZipMiddleware| replace:: ``GZipMiddleware``
   __ https://docs.djangoproject.com/en/stable/ref/middleware/#django.middleware.gzip.GZipMiddleware

API
---

``django_http_compression.middleware.HttpCompressionMiddleware``
^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^

This middleware is similar to Django’s |GZipMiddleware2|__, but with extra coding support.
It compresses responses with one of three codings, depending on what the client supports per the request’s |accept-encoding|__ header:

.. |GZipMiddleware2| replace:: ``GZipMiddleware``
__ https://docs.djangoproject.com/en/stable/ref/middleware/#django.middleware.gzip.GZipMiddleware

.. |accept-encoding| replace:: ``Accept-Encoding``
__ https://developer.mozilla.org/en-US/docs/Web/HTTP/Headers/Accept-Encoding

* Zstandard (``zstd``) - on Python 3.14+.

* Brotli (``br``) - if the ``brotli`` extra is installed.

* Gzip (``gzip``)

See |the MDN content-encoding documentation|__ for more details on these codings and their browser support.

.. |the MDN content-encoding documentation| replace:: the MDN ``content-encoding`` documentation
__ https://developer.mozilla.org/en-US/docs/Web/HTTP/Reference/Headers/Content-Encoding

Codings are prioritized based on any ``q`` factors sent by the client, for example ``accept-encoding: gzip;q=1.0, br;q=0.9`` will prefer gzip over Brotli.
After that, the middleware prefers the algorithms in the order of the above list, with Zstandard being the most preferred.
This is because it’s the most performant, offering similar compression to Brotli in about half the time (per `CloudFlare’s testing <https://blog.cloudflare.com/new-standards/#introducing-zstandard-compression>`__).

In practice, modern browsers do not send ``q`` factors and nearly all support Zstandard, so that will generally be selected (on Python 3.14+).

The middleware skips compression if any of the following are true:

* The content body is less than 200 bytes.
* The response already has a ``Content-Encoding`` header.
* The request does not have a supported ``accept-encoding`` header.
* Compression lengthens the response (for non-streaming responses).

If the response has an ``etag`` header, the ``etag`` is made weak to comply with `RFC 9110 Section 8.8.1 <https://datatracker.ietf.org/doc/html/rfc9110.html#section-8.8.1>`__.

For the Gzip coding, the middleware mitigates some attacks using the *Heal the Breach (HTB)* technique, as used in Django’s ``GzipMiddleware``.
This fix adds a small number of random bytes to each response.
To change the maximum number of random bytes added to responses, subclass the middleware and change the ``gzip_max_random_bytes`` attribute appropriately (default 100).

History
-------

Django has supported Gzip compression since before version 1.0, from `this commit <https://github.com/django/django/commit/8fd94405b51298e84fea604f339b8147df583270>`__ (2005).
Since then, compression on the web has evolved in Brotli (2013) and Zstandard (2015), with browsers adding support for both.

Brotli support on Python has always required a third-party package, making it a little inconvenient.
But with Python 3.14 adding Zstandard support to the standard library, it’s much easier to support a modern, efficient compression algorithm.

This project exists as an evolution of Django’s ``GZipMiddleware``, with the aim to provide a base for adding (at least) Zstandard support to Django itself.
It pulls inspiration from the `django-compression-middleware package <https://pypi.org/project/django-compression-middleware/>`__.

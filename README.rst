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

----

**Work smarter and faster** with my book `Boost Your Django DX <https://adamchainz.gumroad.com/l/byddx>`__ which covers many ways to improve your development experience.

----

Requirements
------------

Python 3.9 to 3.14 supported.

Python 3.14+ required for Zstandard support (for |compression.zstd|__).

.. |compression.zstd| replace:: ``compression.zstd``
__ https://docs.python.org/3/whatsnew/3.14.html#pep-784-zstandard-support-in-the-standard-library

Django 4.2 to 6.0 supported.

Installation
------------

1. Install with **pip**:

   .. code-block:: sh

       python -m pip install django-http-compression

  To include Brotli support, add the ``brotli`` extra to pull in the `brotli <https://pypi.org/project/Brotli/>`__ package:

  .. code-block:: sh

      python -m pip install 'django-http-compression[brotli]'

  Brotli support is recommended only on Python 3.13 and below.
  From Python 3.14, the standard library includes Zstandard support, which is more performant than Brotli and has wide browser support.

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

This middleware compresses responses with Zstandard, Brotli, or Gzip, depending on what the client supports per the request’s |accept-encoding|__ header.
It acts like Django’s |GZipMiddleware2|__, but with the extra algorithms.

.. |accept-encoding| replace:: ``Accept-Encoding``
__ https://developer.mozilla.org/en-US/docs/Web/HTTP/Headers/Accept-Encoding

.. |GZipMiddleware2| replace:: ``GZipMiddleware``
__ https://docs.djangoproject.com/en/stable/ref/middleware/#django.middleware.gzip.GZipMiddleware

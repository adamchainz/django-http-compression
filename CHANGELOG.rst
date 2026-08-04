=========
Changelog
=========

Unreleased
----------

* Support Python 3.15.

* Add Django 6.1 support.

* Drop Django 4.2 to 5.1 support.

* Switch package build backend from setuptools to `uv_build <https://docs.astral.sh/uv/concepts/build-backend/>`__.
  This makes builds with uv about nine times faster, since uv runs the backend natively, without creating a build environment or spawning a Python process.
  Additionally, source distributions no longer include test files, which setuptools previously included incompletely, missing the files needed to actually run them.

1.4.0 (2026-04-08)
------------------

* Expand the **Heal the Breach mitigation** to all encodings, rather than just Gzip (as previously copied from Django).
  This is done by setting an ``x-noise`` header on all compressed responses, which contains a random token of between 0 and 99 bytes, Base64-encoded.

  Thanks to Andreas Pelme for the suggested implementation in `Issue #14 <https://github.com/adamchainz/django-http-compression/issues/14>`__, and to Jacob Walls and Jake Howard of the Django security team for their input.

1.3.0 (2026-04-08)
------------------

* Use Brotli quality level 4 for asynchronous streaming responses.
  The previous fix in version 1.2.0 only affected synchronous streaming responses.

  `PR #46 <https://github.com/adamchainz/django-http-compression/pull/46>`__.

* Excluded ``font/woff`` and ``font/woff2`` from compressible content types, since these formats are already internally compressed.

  `PR #47 <https://github.com/adamchainz/django-http-compression/pull/47>`__.

* Fix ``*`` in ``accept-encoding`` header overriding explicitly listed encodings.

  `PR #48 <https://github.com/adamchainz/django-http-compression/pull/48>`__.

* Drop Python 3.9 support.

1.2.0 (2025-10-26)
------------------

* Limit compression to known-compressible content types, such as ``application/json`` and all ``text/`` content types.
  This avoids wasting resources compressing already-compressed content like images and PDFs.
  The list of compressible content types was seede from Caddy.

  `PR #26 <https://github.com/adamchainz/django-http-compression/pull/26>`__.

* Use Brotli quality 4 for streaming responses as well, which is ~100 times faster than the default quality, 11.

  `PR #18 <https://github.com/adamchainz/django-http-compression/pull/18>`__.

* Decrease minimum length for compression to 50 bytes, copying `CloudFlare’s behaviour <https://developers.cloudflare.com/speed/optimization/content/compression/#:~:text=Minimum%20response%20size%20for%20compression>`__.

  `PR #25 <https://github.com/adamchainz/django-http-compression/pull/25>`__.

* Add a system check warning (``django_http_compression.W001``) when Django’s ``GZipMiddleware`` or `django-compression-middleware <https://pypi.org/project/django-compression-middleware/>`__\’s ``CompressionMiddleware`` are also in use.

  `PR #19 <https://github.com/adamchainz/django-http-compression/pull/19>`__.

1.1.0 (2025-10-15)
------------------

* Add Zstandard support on Python < 3.14 via the `backports-zstd package <https://pypi.org/project/backports-zstd/>`__.

  Thanks to Ertuğrul Keremoğlu in `PR #16 <https://github.com/adamchainz/django-http-compression/pull/16>`__.

1.0.0 (2025-10-10)
------------------

* Initial release.

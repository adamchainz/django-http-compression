=========
Changelog
=========

Unreleased
----------

* Drop Python 3.10 support.

* Support Python 3.15.

* Add Django 6.1 support.

* Drop Django 4.2 to 5.1 support.

* Skip compressing responses with status codes that can’t have content: 1xx, 204, and 304, per `RFC 9110 Section 6.4.1 <https://www.rfc-editor.org/rfc/rfc9110#section-6.4.1-8>`__.
  Previously, empty streaming responses with these statuses gained a compressed body.
  304 responses now always get ``Vary: accept-encoding``, matching the 200 response they stand in for, per `RFC 9110 Section 15.4.5 <https://www.rfc-editor.org/rfc/rfc9110#section-15.4.5>`__.

  `PR #74 <https://github.com/adamchainz/django-http-compression/pull/74>`__.
  Thanks to Thibaut Decombe for the report in `Issue #73 <https://github.com/adamchainz/django-http-compression/issues/73>`__ and cherith for the initial work.

* Support Python 3.14+ builds without ``libzstd``, such as on Azure App Service.
  The middleware now falls back to ``backports.zstd`` if it’s installed, and otherwise disables Zstandard.
  Previously, importing the middleware crashed.

  `PR #83 <https://github.com/adamchainz/django-http-compression/pull/83>`__.
  Thanks to Jason Christa for the report in `Issue #68 <https://github.com/adamchainz/django-http-compression/issues/68>`__ and to Xia Jiang for initial work in `PR #72 <https://github.com/adamchainz/django-http-compression/pull/72>`__.

* Allow subclasses to override compression levels with the ``zstandard_compression_level``, ``brotli_compression_quality``, and ``gzip_compression_level`` attributes.

  `Issue #13 <https://github.com/adamchainz/django-http-compression/issues/13>`__.

* Treat ``x-gzip`` in ``Accept-Encoding`` as equivalent to ``gzip``, per `RFC 9110 Section 8.4.1.3 <https://www.rfc-editor.org/rfc/rfc9110#section-8.4.1.3>`__.

* Skip compressing partial responses, with status code 206, since byte ranges refer to the encoded content, per `RFC 9110 Section 14.4 <https://www.rfc-editor.org/rfc/rfc9110#section-14.4>`__.

* Parse ``Accept-Encoding`` case-insensitively, per `RFC 9110 Section 8.4.1 <https://www.rfc-editor.org/rfc/rfc9110#section-8.4.1>`__.

* Avoid compressing WOFF fonts served with the legacy content type ``application/font-woff``, as WhiteNoise does, since they’re already compressed.

* Fix the ``django_http_compression.W001`` system check, which never triggered because it looked for the wrong middleware name.

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

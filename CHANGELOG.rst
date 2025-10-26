=========
Changelog
=========

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

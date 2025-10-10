from __future__ import annotations

from django.urls import path

from tests import views

urlpatterns = [
    path("", views.index),
    path("short/", views.short),
    path("encoded/", views.encoded),
    path("async/", views.async_),
    path("streaming/", views.streaming),
    path("streaming/empty/", views.streaming_empty),
    path("streaming/blanks/", views.streaming_blanks),
    path("async/streaming/", views.async_streaming),
    path("async/streaming/empty/", views.async_streaming_empty),
    path("async/streaming/blanks/", views.async_streaming_blanks),
    path("binary/", views.binary),
    path("etag/", views.etag),
]

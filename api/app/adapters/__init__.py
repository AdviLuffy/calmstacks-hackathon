"""P3 adapters: the only place teammate engines are imported and wrapped.

``app.services.registry`` is the only module that imports this package, and nothing under
``app.routers`` imports it at all. An adapter never raises into the request path: an
unusable engine becomes an explicit ``unavailable``/``failed`` stage result.
"""

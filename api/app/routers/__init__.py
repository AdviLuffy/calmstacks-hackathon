"""P3 HTTP routers. A router never imports an adapter, an engine or a store implementation.

Every dependency is resolved from ``request.app.state`` through :mod:`app.dependencies`.
"""

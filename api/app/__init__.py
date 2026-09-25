"""TRACE investigator API (Person 3: Investigator Experience & Integration).

Dependency direction:

    HTTP routers  ->  orchestration pipeline  ->  service interfaces (Protocols)
                                                    ^
                                                    | implemented by
                                         services/mocks.py, services/unavailable.py,
                                         adapters/recovery_adapter.py, adapters/ai_adapter.py
                                                    ^
                                         services/registry.py  (the ONLY module that
                                                                imports adapters/engines)

No router imports an adapter or a teammate implementation. No teammate module needs
FastAPI or Pydantic in order to integrate with this API.
"""

__all__ = ["__version__"]

__version__ = "0.1.0"
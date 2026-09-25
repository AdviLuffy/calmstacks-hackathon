"""Local application runner for TRACE forensic evidence system.

Starts the FastAPI server with both real P1 and P2 engines connected.
Provides the multi-page forensic workspace at http://127.0.0.1:8000/
"""

from __future__ import annotations

import os
import sys
from pathlib import Path

# Add project modules to Python path
ROOT_DIR = Path(__file__).resolve().parent
sys.path.insert(0, str(ROOT_DIR / "evidence" / "src"))
sys.path.insert(0, str(ROOT_DIR / "api"))
sys.path.insert(0, str(ROOT_DIR))

# Wire real P1 Recovery Engine and P2 Intelligence Engine by default
os.environ.setdefault("TRACE_RECOVERY_ENGINE", "trace_evidence.engine:TraceEvidenceEngine")
os.environ.setdefault("TRACE_AI_ENGINE", "trace.intel.engine:TraceIntelligenceEngine")
os.environ.setdefault("TRACE_RECOVERY_MODE", "real")
os.environ.setdefault("TRACE_AI_MODE", "real")
os.environ.setdefault("TRACE_PERSIST_SESSIONS", "true")

if __name__ == "__main__":
    import uvicorn

    print("=" * 70)
    print("  TRACE: FORENSIC EVIDENCE & RECONSTRUCTION WORKSPACE")
    print("=" * 70)
    print("  Subsystems integrated:")
    print("    [P1] Evidence & Reconstruction Engine (trace-evidence v0.1.0)")
    print("    [P2] M0 Frozen Contract & Intel Engine (trace-intel v1.0.0)")
    print("    [P3] Investigator API & Forensic Workspace (FastAPI v0.1.0)")
    print("")
    print("  Brand Homepage:   http://127.0.0.1:8000/")
    print("  Investigations:   http://127.0.0.1:8000/investigations")
    print("  New Analysis:     http://127.0.0.1:8000/investigations/new")
    print("  Interactive Docs: http://127.0.0.1:8000/docs")
    print("  Health Status:    http://127.0.0.1:8000/api/health")
    print("=" * 70)
    print("  Press Ctrl+C to stop the server.")
    print("")

    uvicorn.run("app.main:app", host="127.0.0.1", port=8000, reload=False)

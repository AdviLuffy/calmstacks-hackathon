"""Vercel Serverless ASGI entrypoint for TRACE Investigator API."""

import os
import sys
from pathlib import Path

# Add modules to sys.path for serverless environment
ROOT_DIR = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT_DIR / "evidence" / "src"))
sys.path.insert(0, str(ROOT_DIR / "trace" / "intel" / "src"))
sys.path.insert(0, str(ROOT_DIR / "api"))
sys.path.insert(0, str(ROOT_DIR))

# Ensure real engines are wired in serverless demo mode
os.environ.setdefault("TRACE_RECOVERY_ENGINE", "trace_evidence.engine:TraceEvidenceEngine")
os.environ.setdefault("TRACE_AI_ENGINE", "trace.intel.engine:TraceIntelligenceEngine")
os.environ.setdefault("TRACE_RECOVERY_MODE", "real")
os.environ.setdefault("TRACE_AI_MODE", "real")
os.environ.setdefault("TRACE_PERSIST_SESSIONS", "false")

# Ensure writable temp directories in serverless environment
if os.environ.get("VERCEL"):
    os.environ.setdefault("TRACE_SESSION_ROOT", "/tmp/trace_sessions")
    os.environ.setdefault("TRACE_EVIDENCE_ROOT", "/tmp/trace_evidence")

from app.main import app

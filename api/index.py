"""Vercel Serverless ASGI entrypoint for TRACE Investigator API."""

import os
import sys
from pathlib import Path

# Add modules to sys.path for serverless environment
ROOT_DIR = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT_DIR / "evidence" / "src"))
sys.path.insert(0, str(ROOT_DIR / "api"))
sys.path.insert(0, str(ROOT_DIR))

# Ensure real engines are wired in serverless demo mode
os.environ.setdefault("TRACE_RECOVERY_ENGINE", "trace_evidence.engine:TraceEvidenceEngine")
os.environ.setdefault("TRACE_AI_ENGINE", "trace.intel.engine:TraceIntelligenceEngine")
os.environ.setdefault("TRACE_RECOVERY_MODE", "real")
os.environ.setdefault("TRACE_AI_MODE", "real")

from app.main import app

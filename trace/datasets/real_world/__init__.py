"""TRACE Real-World PDF Dataset Integration (Phase 10).

Provides:
- Registry for open-access research papers (arXiv CC-BY, SafeDocs, Public Domain)
- Controlled corruptor with document-level split isolation
- Genuinely damaged corpus manager
- Safe, rate-limited downloader with manual download checklist generation
- Sample collection curator
"""

from trace.datasets.real_world.controlled_corruptor import ControlledCorruptor
from trace.datasets.real_world.curator import SampleDatasetCurator
from trace.datasets.real_world.downloader import RealWorldDocumentDownloader
from trace.datasets.real_world.genuine_damaged import GenuinelyDamagedCorpusManager
from trace.datasets.real_world.registry import RealWorldRegistryManager

__all__ = [
    "RealWorldRegistryManager",
    "RealWorldDocumentDownloader",
    "SampleDatasetCurator",
    "ControlledCorruptor",
    "GenuinelyDamagedCorpusManager",
]

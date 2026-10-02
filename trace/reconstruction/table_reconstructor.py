"""Table Reconstructor for TRACE Phase 9.

Recovers tabular data, grid structures, rows, columns, headers, and cell
alignments from damaged PDF evidence with strict forensic provenance.
"""

from __future__ import annotations

import re
from typing import Any, Dict, List, Optional, Sequence, Tuple

from trace.multimodal.representation import (
    BoundingBox,
    DocumentElement,
    ElementType,
    ProvenanceCategory,
)
from trace.reconstruction.models import TableCell, TableRow, TableStructure


class TableReconstructor:
    """Detects, parses, and reconstructs structured tables from recovered PDF elements."""

    def __init__(self, min_rows: int = 2, min_cols: int = 2) -> None:
        self.min_rows = min_rows
        self.min_cols = min_cols

    def detect_table_from_text_lines(
        self,
        text_lines: Sequence[str],
        page_number: int = 1,
        source_offset: int = 0,
        table_idx: int = 1,
    ) -> Optional[TableStructure]:
        """Detect and reconstruct a table from candidate text lines with columns."""
        if len(text_lines) < self.min_rows:
            return None

        # Look for explicit table caption
        caption: Optional[str] = None
        table_rows_raw: List[str] = []

        for line in text_lines:
            t = line.strip()
            if not t:
                continue
            if re.match(r"^(?:Table|Tab\.)\s*[0-9IVX]+[\s\.:\-]*(.*)", t, re.IGNORECASE):
                caption = t
            else:
                table_rows_raw.append(t)

        if len(table_rows_raw) < self.min_rows:
            return None

        # Determine column delimiter: pipe '|', tab '\t', or multi-space (2+ spaces)
        sample_text = "\n".join(table_rows_raw[:5])
        if "|" in sample_text:
            delimiter = "|"
        elif "\t" in sample_text:
            delimiter = "\t"
        else:
            # Check for multiple spaces
            space_split_counts = [len(re.split(r"\s{2,}", line.strip())) for line in table_rows_raw]
            if space_split_counts and max(space_split_counts) >= self.min_cols:
                delimiter = r"\s{2,}"
            else:
                return None

        # Parse rows
        parsed_rows: List[List[str]] = []
        for line in table_rows_raw:
            if delimiter == "|":
                cols = [c.strip() for c in line.split("|")]
                # Strip leading/trailing empty splits if row starts/ends with '|'
                if cols and not cols[0]:
                    cols.pop(0)
                if cols and not cols[-1]:
                    cols.pop(-1)
            elif delimiter == "\t":
                cols = [c.strip() for c in line.split("\t")]
            else:
                cols = [c.strip() for c in re.split(delimiter, line.strip())]

            if len(cols) >= self.min_cols:
                parsed_rows.append(cols)

        if len(parsed_rows) < self.min_rows:
            return None

        max_cols = max(len(r) for r in parsed_rows)
        table_rows: List[TableRow] = []
        unrecoverable_cells = 0

        for r_idx, row in enumerate(parsed_rows):
            is_header = (r_idx == 0)
            cells: List[TableCell] = []
            for c_idx in range(max_cols):
                text_val = row[c_idx] if c_idx < len(row) else ""
                is_empty = not bool(text_val.strip())
                if is_empty:
                    unrecoverable_cells += 1

                cell = TableCell(
                    row_idx=r_idx,
                    col_idx=c_idx,
                    text=text_val,
                    bbox=None,
                    is_header=is_header,
                    is_empty=is_empty,
                    confidence=1.0 if not is_empty else 0.5,
                    provenance=ProvenanceCategory.AUTHENTIC if not is_empty else ProvenanceCategory.DETERMINISTIC,
                )
                cells.append(cell)

            table_rows.append(TableRow(row_idx=r_idx, cells=cells, is_header=is_header))

        table_id = f"table_{table_idx}_p{page_number}"
        return TableStructure(
            table_id=table_id,
            page_number=page_number,
            rows=table_rows,
            cols_count=max_cols,
            rows_count=len(table_rows),
            bbox=BoundingBox(x1=54.0, y1=200.0, x2=558.0, y2=200.0 + (len(table_rows) * 20.0), coord_unit="pt"),
            caption=caption,
            confidence=0.95,
            provenance=ProvenanceCategory.DETERMINISTIC,
            unrecoverable_cells_count=unrecoverable_cells,
            source_offsets=[[source_offset, source_offset + 100]],
        )

    def to_document_element(self, table: TableStructure) -> DocumentElement:
        """Convert TableStructure to standard DocumentElement."""
        # Convert rows to serializable dict
        table_dict = {
            "cols_count": table.cols_count,
            "rows_count": table.rows_count,
            "caption": table.caption,
            "headers": [c.text for c in table.rows[0].cells] if table.rows else [],
            "rows": [[c.text for c in r.cells] for r in table.rows],
            "unrecoverable_cells": table.unrecoverable_cells_count,
        }

        return DocumentElement(
            element_id=table.table_id,
            type=ElementType.TABLE,
            page_number=table.page_number,
            bbox=table.bbox,
            content=table_dict,
            reading_order_index=None,
            confidence=table.confidence,
            provenance=table.provenance,
            source="pdf_recovery.tabular_reconstruction",
            evidence_offsets=table.source_offsets,
            metadata={
                "cols_count": table.cols_count,
                "rows_count": table.rows_count,
                "caption": table.caption,
                "unrecoverable_cells": table.unrecoverable_cells_count,
            },
        )

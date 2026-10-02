import json
from pathlib import Path
from trace.datasets.real_world.corpus_builder import CORPUS_ROOT, MANIFEST_PATH
from trace_evidence.pdf_recovery import GeneralizedPdfRecoveryEngine
from trace_evidence.repair import validate_and_render_pdf

manifest = json.loads(MANIFEST_PATH.read_text(encoding="utf-8"))
items = manifest["items"]
print(f"Evaluating {len(items)} corpus items...")
success_count = 0
for item in items:
    cid = item["corpus_id"]
    fn = item["corrupted_filename"]
    fpath = CORPUS_ROOT / "damaged" / fn
    data = fpath.read_bytes()
    eng = GeneralizedPdfRecoveryEngine(data)
    repaired, synth, meta = eng.recover()
    is_open, pages, txt, err = validate_and_render_pdf(repaired)
    status = "PASS" if is_open and pages >= 1 else "FAIL"
    if is_open and pages >= 1:
        success_count += 1
    sample_snippet = (txt[:40] + "...") if txt else "(no text extracted)"
    print(f"[{status}] {cid:32} | pages={pages} | open={is_open} | text='{sample_snippet}'")

print(f"\nTotal recovered: {success_count}/{len(items)} ({success_count/len(items)*100:.1f}%)")

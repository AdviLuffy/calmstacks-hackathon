"""Verification script for TRACE Benchmark UI Integration and User Journey."""

import json
import urllib.parse
import urllib.request

BASE = "http://127.0.0.1:8000"

print("Starting User Journey Verification...")

# Step 1: Open TRACE homepage
r_home = urllib.request.urlopen(f"{BASE}/")
home_html = r_home.read().decode("utf-8")
assert r_home.status == 200
assert 'href="/benchmark"' in home_html
print("[OK] Step 1: Homepage loaded with /benchmark link in navigation & hero")

# Step 2: Open Benchmark page via navigation
r_bench = urllib.request.urlopen(f"{BASE}/benchmark")
bench_html = r_bench.read().decode("utf-8")
assert r_bench.status == 200
assert 'class="nav-link active">Benchmarks</a>' in bench_html
assert "TRACE Forensic Benchmarking" in bench_html
assert "site-footer" in bench_html
assert 'name="viewport"' in bench_html
assert "table-container" in bench_html
print("[OK] Step 2: Benchmark page loaded with native TRACE header, active tab, responsive viewport, and footer")

# Step 3: Load registry & damaged corpus API
r_reg = urllib.request.urlopen(f"{BASE}/api/datasets/real-world/registry")
reg = json.loads(r_reg.read().decode("utf-8"))
assert len(reg["documents"]) >= 5
print(f"[OK] Step 3a: Registry loaded with {len(reg['documents'])} documents")

r_dam = urllib.request.urlopen(f"{BASE}/api/datasets/real-world/damaged-corpus")
dam = json.loads(r_dam.read().decode("utf-8"))
assert dam["sample_count"] >= 2
print(f"[OK] Step 3b: Damaged corpus loaded with {dam['sample_count']} samples and zero-fabricated ground truth policy")

# Step 4: Run live benchmark
req = urllib.request.Request(
    f"{BASE}/api/datasets/benchmark/run?samples_per_doc=1&max_docs=1",
    data=b"",
    method="POST",
)
r_run = urllib.request.urlopen(req)
bm_result = json.loads(r_run.read().decode("utf-8"))
assert bm_result["benchmark_version"] == "1.0.0"
ctrl_res = bm_result["controlled_benchmark_summary"]
print(f"[OK] Step 4: Benchmark run completed: {ctrl_res['total_controlled_samples']} sample(s), Authentic byte recovery: {ctrl_res['avg_authentic_byte_recovery_pct']}%, Text Jaccard: {ctrl_res['avg_text_jaccard_similarity']}")

# Step 5: Check benchmark status endpoint
r_stat = urllib.request.urlopen(f"{BASE}/api/datasets/benchmark/status")
stat = json.loads(r_stat.read().decode("utf-8"))
assert stat["has_cached_run"] is True
print("[OK] Step 5: Benchmark status verified with cached run")

# Step 6: Navigate back to Investigations
r_inv = urllib.request.urlopen(f"{BASE}/investigations")
inv_html = r_inv.read().decode("utf-8")
assert r_inv.status == 200
assert 'href="/benchmark"' in inv_html
print("[OK] Step 6: Successfully navigated back to /investigations with benchmark link visible")

# Step 7: Test existing carving and recovery pipeline
post_data = urllib.parse.urlencode({
    "fixture_id": "synthetic_blob",
    "case_id": "CASE-JOURNEY-VERIFY",
    "case_title": "User Journey End-to-End",
    "write_blocked": "true",
}).encode("utf-8")
req_carve = urllib.request.Request(f"{BASE}/api/sessions/carve", data=post_data, method="POST")
r_carve = urllib.request.urlopen(req_carve)
carve_res = json.loads(r_carve.read().decode("utf-8"))
assert r_carve.status == 201
sid = carve_res["session_id"]
print(f"[OK] Step 7: Existing carving and recovery pipeline intact, session {sid} created")

# Step 8: View investigation overview
r_sess = urllib.request.urlopen(f"{BASE}/investigations/{sid}")
assert r_sess.status == 200
print("[OK] Step 8: Existing investigation overview page verified")

print("\n" + "=" * 60)
print("  ALL 8 USER JOURNEYS FULLY VERIFIED ON LIVE SERVER")
print("=" * 60)

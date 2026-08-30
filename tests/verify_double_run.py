import hashlib
import subprocess
import sys
from pathlib import Path

outputs_dir = Path("outputs")
audit_dir = Path("audit")

files_to_check = [
    outputs_dir / "work_orders.jsonl",
    outputs_dir / "comms_pending.jsonl",
    outputs_dir / "comms_sent.jsonl",
    outputs_dir / "quarantine.jsonl",
    audit_dir / "audit.jsonl"
]

def get_hashes():
    hashes = {}
    for f in files_to_check:
        if f.exists():
            with open(f, "rb") as fp:
                hashes[f.name] = hashlib.sha256(fp.read()).hexdigest()
        else:
            hashes[f.name] = None
    return hashes

print("--- EXECUTING RUN 1 ---")
res1 = subprocess.run([sys.executable, "run_pipeline.py", "--eval-mode"], capture_output=True, text=True)
if res1.returncode != 0:
    print(f"Run 1 failed with code {res1.returncode}:\n{res1.stderr}")
    sys.exit(1)

h1 = get_hashes()
for k, v in h1.items():
    print(f"{k:25s}: {v}")

print("\n--- EXECUTING RUN 2 (Back-to-Back) ---")
res2 = subprocess.run([sys.executable, "run_pipeline.py", "--eval-mode"], capture_output=True, text=True)
if res2.returncode != 0:
    print(f"Run 2 failed with code {res2.returncode}:\n{res2.stderr}")
    sys.exit(1)

h2 = get_hashes()
for k, v in h2.items():
    print(f"{k:25s}: {v}")

print("\n--- VERIFICATION COMPARISON ---")
all_match = True
for k in h1:
    match = (h1[k] == h2[k])
    print(f"[{'MATCH' if match else 'DIFF'}] {k:25s}: {'Identical bit-for-bit' if match else 'Mismatch!'}")
    if not match:
        all_match = False

if all_match:
    print("\n[SUCCESS] 100% Deterministic Idempotency Verified! Zero Drift.")
else:
    print("\n[FAIL] Mismatch detected.")
    sys.exit(1)

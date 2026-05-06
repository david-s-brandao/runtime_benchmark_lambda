#!/usr/bin/env python3
import subprocess
import sys
from pathlib import Path

BASE = Path(__file__).parent.resolve()

def run(cmd, cwd):
    result = subprocess.run(cmd, cwd=cwd, shell=isinstance(cmd, str))
    if result.returncode != 0:
        print(f"Command failed: {cmd}")
        sys.exit(result.returncode)

print("==> Building Python Lambda zips...")
scripts = BASE / "scripts"
run("zip -j producer.zip producer.py", cwd=scripts)
run("zip -j analyzer.zip analyzer.py", cwd=scripts)

print("==> Building Rust processor...")
run("make deploy", cwd=BASE / "src/rust_processor")

print("==> Building Java processor...")
run("mvn package -q", cwd=BASE / "src/java_processor")

print()
answer = input("Deploy with Terraform? [y/N] ").strip().lower()
if answer != "y":
    print("Skipping deploy.")
    sys.exit(0)

print("\nEnter S3 bucket names (must be globally unique):")
bucket_input  = input("  Input images bucket:  ").strip()
bucket_output = input("  Output images bucket: ").strip()
bucket_logs   = input("  Logs bucket:          ").strip()

run(
    [
        "terraform", "plan",
        f"-var=bucket_input={bucket_input}",
        f"-var=bucket_output={bucket_output}",
        f"-var=bucket_logs={bucket_logs}",
    ],
    cwd=BASE / "terraform",
)

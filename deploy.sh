#!/usr/bin/env bash
set -e

BASE_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"

echo "==> Building Python Lambda zips..."
cd "$BASE_DIR/scripts"
zip -j producer.zip producer.py
zip -j analyzer.zip analyzer.py

echo "==> Building Rust processor..."
cd "$BASE_DIR/src/rust_processor"
make deploy

echo "==> Building Java processor..."
cd "$BASE_DIR/src/java_processor"
mvn package -q

echo ""
read -rp "Deploy with Terraform? [y/N] " answer
if [[ ! "$answer" =~ ^[Yy]$ ]]; then
    echo "Skipping deploy."
    exit 0
fi

echo ""
echo "Enter S3 bucket names (must be globally unique):"
read -rp "  Input images bucket:  " BUCKET_INPUT
read -rp "  Output images bucket: " BUCKET_OUTPUT
read -rp "  Logs bucket:          " BUCKET_LOGS

cd "$BASE_DIR/terraform"
terraform plan \
    -var "bucket_input=$BUCKET_INPUT" \
    -var "bucket_output=$BUCKET_OUTPUT" \
    -var "bucket_logs=$BUCKET_LOGS"

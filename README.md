# Serverless Image Processing Benchmark

FinOps is no longer just about cost monitoring; it is about architectural efficiency. While AWS Lambda provides a highly scalable serverless execution model, the choice of runtime language introduces significant, often hidden, financial and performance trade-offs at scale.

Traditional enterprise languages like Java rely on heavy JVMs, leading to severe cold starts and inflated memory billing. In contrast, systems languages like Rust promise bare-metal performance with a minimal footprint. This benchmark exposes the exact infrastructure, latency, and cost multipliers when running an event-driven architecture (SQS & Lambda) using Java 21 versus Rust.

## TL;DR

Rust completely outperformed Java across all metrics in this sustained high-concurrency benchmark (~1,000+ invocations per function)

- **Cold Starts:** Rust is 10x faster (175ms average vs. Java's 1,814ms).
- **Memory Footprint:** Both functions were allocated an identical 512MB. Rust consumed only ~43MB of that budget versus Java's ~199MB — a 78% reduction driven purely by runtime efficiency, not configuration.
- **Performance & Tail Latency:** Rust is consistently faster. Its median execution (p50) is twice as fast (254ms vs. 497ms), but the real difference is at scale — Java's p99 latency spikes to over 8 seconds, while Rust stays under 3.7 seconds even at extreme percentiles.
- **Billing:** Rust generated 73% less total billed duration (399k ms vs. 1.49M ms).

## Architecture and Flow

The benchmark simulates a real-world, event-driven image processing pipeline. To ensure absolute fairness, the architecture employs a Fanout pattern, guaranteeing both languages receive the exact same workload at the exact same millisecond.

```mermaid
graph LR
    EB[EventBridge Cron] -->|30m Trigger| NL(Notification Lambda)
    NL -->|Publishes 100 Events| SNS{SNS Topic Fanout}
    
    SNS -->|Sub| SQS_J[SQS Queue Java]
    SNS -->|Sub| SQS_R[SQS Queue Rust]
    
    SQS_J -->|Batch Size 1| L_J(Java 21 Lambda)
    SQS_R -->|Batch Size 1| L_R(Rust Lambda)
    
    L_J -->|Saves Processed Image| S3_Out[(S3 Output Bucket)]
    L_R -->|Saves Processed Image| S3_Out
    
    L_J -.->|Writes Telemetry| CW[CloudWatch Logs & X-Ray]
    L_R -.->|Writes Telemetry| CW
    
    LL(Logs Lambda) -.->|Fetches Metrics Daily| CW
    LL -.->|Saves JSON Report| S3_Out
```

### The Workload

- **Trigger:** Batches of 100 image processing events are dispatched to the Lambda functions every 30 minutes. This interval intentionally forces periodic environment destruction, ensuring a reliable cold start measurement alongside concurrent warm executions.
- **Processing:** Upon invocation, the functions execute CPU-intensive tasks to download the image, apply a 70% compression algorithm, and upload the result back to S3.

<br>
<p align="center">
  <b>Original Image (800x600)</b><br>
  <img src="images/original_images/image_10.jpg" width="55%" alt="Original Image">
</p>
<p align="center">
  <img src="images/processed_images/Java_lambda_image_10.jpg" width="45%" alt="Java Processed Image">
  <img src="images/processed_images/Rust_lambda_image_10.jpg" width="45%" alt="Rust Processed Image">
  <br>
  <i>Left: Java 21 Output (70%) &nbsp;&nbsp; | &nbsp;&nbsp; Right: Rust Output (70%)</i>
</p>
<br>

## Environment & Methodology

Both functions were subjected to the exact same AWS environment constraints and IaC configurations:

- **Region:** `us-east-1`
- **Architecture:** `x86_64`
- **Allocated Memory:** 512 MB per function — identical for both. Memory consumption differences reflect runtime behavior, not configuration.
- **Concurrency Limit:** Unreserved (-1) to allow free horizontal scaling.
- **Event Source Mapping:** SQS Batch Size set to `1` to force maximum concurrency.
- **Runtimes:** Java 21 (Managed Runtime) vs. Rust (Edition 2021 on `provided.al2023` Custom Runtime).
- **SnapStart:** Explicitly disabled for Java. SnapStart is a deployment-time optimization that requires opt-in and additional engineering overhead; excluding it reflects the default production experience for Java Lambda functions.

Performance and trace data were extracted directly from AWS using CloudWatch Logs and AWS X-Ray via an automated consolidation script. The sample size consists of 1,026 invocations for Java and 1,028 for Rust, capturing both cold starts and warm executions under aggressive parallel load.

## Detailed Results

### 1. Cold Starts (Init Duration)

| Metric | Java 21 | Rust |
|--------|---------|------|
| **Cold Start Count** | 116 (11.3%) | 96 (9.4%) |
| **Average** | 1814.78 ms | 175.26 ms |
| **p50 (Median)** | 1770.93 ms | 171.88 ms |
| **p90** | 2065.62 ms | 198.07 ms |
| **p99** | 2368.75 ms | 253.64 ms |
| **Maximum** | 2395.67 ms | 253.64 ms |

### 2. Warm Starts (Total Execution Duration)

| Metric | Java 21 | Rust |
|--------|---------|------|
| **Average** | 1248.19 ms | 370.44 ms |
| **p50 (Median)** | 497.15 ms | 254.23 ms |
| **p90** | 4618.30 ms | 605.34 ms |
| **p99** | 8229.60 ms | 3691.89 ms |
| **Maximum** | 15955.58 ms | 6766.31 ms |

### 3. Memory Usage (Peak)

| Metric | Java 21 | Rust |
|--------|---------|------|
| **Average** | ~198.39 MB | ~43.79 MB |
| **Maximum** | ~209.00 MB | ~45.00 MB |

*Both functions were allocated 512MB. Rust naturally consumed ~4.5x less memory — a direct reduction in GB-second billing with zero tuning required.*

### 4. Cost Projection

Based on AWS Lambda pricing (`us-east-1`, x86_64: $0.0000166667 per GB-second) and the observed billed duration delta from this benchmark, the following table projects monthly cost at scale. Memory is normalized to the 512MB allocation used for both functions.

| Monthly Invocations | Java 21 Est. Cost | Rust Est. Cost | Monthly Savings |
|---------------------|-------------------|----------------|-----------------|
| 100,000 | ~$0.71 | ~$0.19 | ~$0.52 |
| 1,000,000 | ~$7.10 | ~$1.90 | ~$5.20 |
| 10,000,000 | ~$71.00 | ~$19.00 | ~$52.00 |
| 100,000,000 | ~$710.00 | ~$190.00 | ~$520.00 |

> **Note:** Projections are based on observed average billed duration per invocation (Java: ~1,452ms, Rust: ~389ms at 512MB). Free tier, request charges, and data transfer costs are excluded. Real-world savings will vary with workload distribution.

### Comparative Summary

| Metric | Java | Rust | Advantage |
|--------|------|------|-----------|
| **Average Cold Start** | 1814 ms | 175 ms | Rust is 10.3x faster |
| **Median Duration (p50)** | 497 ms | 254 ms | Rust is ~2x faster |
| **Peak Memory (natural)** | ~199 MB | ~43 MB | Rust uses 4.6x less (same 512MB allocation) |
| **Infrastructure Scaling** | High Concurrency | Low Concurrency | Rust clears the SQS backlog faster |

## Code Complexity Trade-off

Rust's performance advantages come with real engineering costs. This section gives an honest picture of both sides.

### Dependency & Build Footprint

| Aspect | Java 21 | Rust |
|--------|---------|------|
| **Build Tool** | Maven (`pom.xml`) | Cargo (`Cargo.toml`) |
| **Runtime** | Managed (AWS-provided JRE) | Custom (`provided.al2023` + bootstrap binary) |
| **Deployment Package** | Fat JAR via `maven-shade-plugin` | Cross-compiled binary via `cargo lambda build --release` |
| **Cross-compilation** | Not required | Required (`cargo lambda` or Docker with `cross`) |
| **Compile Time (approx.)** | ~10–20s (incremental) | ~45–90s (full release build) |

Rust's longer compile times are a real CI/CD cost — slower feedback loops and slightly higher build pipeline minutes. For teams shipping frequently, this is worth factoring in.

### Handler Comparison

#### Java 21 Handler
*(Full implementation available in [src/java_processor/]())*

```java
public Void handleRequest(SQSEvent event, Context context) {
    for (SQSEvent.SQSMessage message : event.getRecords()) {
        String filename = message.getBody();
        Segment segment = AWSXRay.beginSegment("java_function");
        
        try {
            // ... [S3 Download & Object mapping omitted for brevity] ...
            BufferedImage original = ImageIO.read(new java.io.ByteArrayInputStream(imageBytes));
            BufferedImage compressed = compress(original, 0.7f);
            // ... [S3 Upload omitted] ...
        } catch (Exception e) {
            segment.addException(e);
            throw new RuntimeException(e);
        } finally {
            AWSXRay.endSegment();
        }
    }
    return null;
}
```

#### Rust Handler
*(Full implementation available in [src/rust_processor/]())*

```rust
async fn handler(event: LambdaEvent<SqsEvent>, s3: S3Client, xray: XRayClient) -> Result<(), Error> {
    for record in event.payload.records {
        let filename = record.body.unwrap_or_default();
        
        // ... [S3 Download omitted for brevity] ...
        // Strict error handling and memory safety enforced at compile time
        let compressed = compress(image::load_from_memory(&image_data)?, 0.7);
        // ... [S3 Upload & Custom XRay segment push omitted] ...
    }
    Ok(())
}
```

The handler logic looks similar at this level of abstraction, but the surface complexity diverges in the build pipeline and operational setup, not the application code itself.

## Limitations & Scope

These results should be interpreted with the following constraints in mind:

- **Workload type:** This benchmark is CPU-bound (image compression). Rust's advantage may be less pronounced for I/O-bound or memory-bound workloads where the bottleneck lies outside the runtime.
- **JVM warmup:** The 30-minute cycle destroys Lambda environments before the JVM can reach sustained peak optimization. In architectures with persistent warm containers (e.g., high-frequency workloads with provisioned concurrency), Java's performance gap would narrow.
- **SnapStart excluded by design:** Java Lambda SnapStart can meaningfully reduce cold start times but requires explicit opt-in and adds deployment complexity. This benchmark reflects the default Java Lambda experience.
- **Single region:** Results were collected in `us-east-1`. Cold start behavior can vary across regions due to Lambda fleet density differences.
- **Single image size/type:** The benchmark used 800×600 JPEG inputs. Results may differ for larger images or different formats.

## Product Structure

```PlainText
runtime_benchmark_lambda/
├── terraform/               # IaC — deploys all AWS resources
├── src/
│   ├── java_processor/      # Java 21 Lambda handler
│   └── rust_processor/      # Rust Lambda handler
├── images/
│   ├── original_images/     # Source images used in benchmark
│   └── processed_images/    # Output from both runtimes
├── reports/                 # Daily JSON reports exported from S3
│
└── scripts/                 # Notification + Logs lambda source code and other scripts
```

## Automated Deployment

Two deploy scripts are provided to build all components and optionally run `terraform plan` in a single command. Both scripts do the same thing — pick the one that matches your OS.

| Script | Platform |
|--------|----------|
| `deploy.sh` | Linux / macOS |
| `deploy.py` | Windows (and Linux / macOS) |

**What they do:**
1. Zip `scripts/producer.py` → `producer.zip` and `scripts/analyzer.py` → `analyzer.zip`
2. Build and zip the Rust Lambda (`make deploy`)
3. Package the Java Lambda (`mvn package`)
4. Ask whether to run `terraform plan` — if yes, prompt for the three S3 bucket names and pass them to Terraform

**Usage:**

```bash
# Linux / macOS
./deploy.sh

# Windows (or any platform with Python 3)
python deploy.py
```

> The scripts only run `terraform plan`. Change the last command to `terraform apply` once you are ready to provision resources.

## Reproducibility

### Test Images

> Each URL is seeded (`/seed/{n}/`), so the images are deterministic — seed 42 will always return the same 800×600 image regardless of when the command is run.

> Images sourced from [Lorem Picsum](https://picsum.photos/) are covered by the [Unsplash License](https://unsplash.com/license) — free for commercial and non-commercial use, no attribution required.

### Infrastructure

The benchmark infrastructure as code (IaC) is available in this repository inside the [`terraform/`](/terraform/) directory. To reproduce these results in your own AWS account:

1. Authenticate your terminal using the AWS CLI.
2. Initialize and deploy the infrastructure using Terraform:

```bash
terraform init
terraform plan
terraform apply
```

3. Trigger the benchmark by either waiting for the EventBridge cron schedule (every 30 minutes) or by manually invoking the Notification Lambda via the AWS Console.

4. Logs Lambda is invoked automatically at 11:00pm (US-East-1 time). If sufficient data is collected earlier, you can export the consolidated JSON metrics manually:

```bash
aws lambda invoke --function-name logs_lambda --payload '{}' response.json \
  --region us-east-1 --cli-binary-format raw-in-base64-out

aws s3 sync s3://logs-lambda-benchmark/ . \
  --exclude "*" --include "*daily_report.json" \
  --region us-east-1
# Note: this will download all daily reports from the bucket
```
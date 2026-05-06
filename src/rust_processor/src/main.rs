use aws_lambda_events::event::sqs::SqsEvent;
use aws_sdk_s3::Client as S3Client;
use aws_sdk_s3::primitives::ByteStream;
use aws_sdk_xray::Client as XRayClient;
use image::{GenericImageView, ImageFormat};
use lambda_runtime::{run, service_fn, Error, LambdaEvent};
use std::io::Cursor;
use std::time::{SystemTime, UNIX_EPOCH};

#[tokio::main]
async fn main() -> Result<(), Error> {
    tracing_subscriber::fmt().with_target(false).without_time().init();
    let config = aws_config::load_defaults(aws_config::BehaviorVersion::latest()).await;
    let s3 = S3Client::new(&config);
    let xray = XRayClient::new(&config);
    run(service_fn(move |event| handler(event, s3.clone(), xray.clone()))).await
}

async fn handler(event: LambdaEvent<SqsEvent>, s3: S3Client, xray: XRayClient) -> Result<(), Error> {
    let bucket_in  = std::env::var("BUCKET_IN")?;
    let bucket_out = std::env::var("BUCKET_OUT")?;

    for record in event.payload.records {
        let filename = record.body.unwrap_or_default();
        tracing::info!("Processing: {}", filename);

        let start = now_secs();

        let image_data = s3.get_object()
            .bucket(&bucket_in)
            .key(&filename)
            .send().await?
            .body.collect().await?
            .into_bytes();

        let compressed = compress(image::load_from_memory(&image_data)?, 0.7);

        let mut buf = Vec::new();
        compressed.write_to(&mut Cursor::new(&mut buf), ImageFormat::Jpeg)?;

        s3.put_object()
            .bucket(&bucket_out)
            .key(format!("Rust_lambda_{}", filename))
            .body(ByteStream::from(buf))
            .send().await?;

        let end = now_secs();

        // Directly put a trace segment — bypasses Sampled=0 from SQS trigger
        let trace_id = format!("1-{:08x}-{:024x}", start as u32, ptr_entropy());
        let segment_id = format!("{:016x}", ptr_entropy());
        let doc = format!(
            r#"{{"name":"rust_function","id":"{segment_id}","trace_id":"{trace_id}","start_time":{start:.3},"end_time":{end:.3},"annotations":{{"filename":"{filename}"}}}}"#
        );
        let _ = xray.put_trace_segments()
            .trace_segment_documents(doc)
            .send().await;

        tracing::info!("Done: {}", filename);
    }

    Ok(())
}

fn now_secs() -> f64 {
    SystemTime::now().duration_since(UNIX_EPOCH).unwrap().as_secs_f64()
}

// Cheap non-crypto entropy from pointer address
fn ptr_entropy() -> u64 {
    let x = Box::new(0u8);
    let addr = &*x as *const u8 as u64;
    addr.wrapping_mul(6364136223846793005).wrapping_add(1442695040888963407)
}

fn compress(img: image::DynamicImage, scale: f32) -> image::DynamicImage {
    let (w, h) = img.dimensions();
    img.resize((w as f32 * scale) as u32, (h as f32 * scale) as u32, image::imageops::FilterType::Lanczos3)
}

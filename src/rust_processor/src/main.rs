use aws_lambda_events::event::sqs::SqsEvent;
use aws_sdk_s3::{primitives::ByteStream, Client};
use image::{imageops::FilterType, DynamicImage, GenericImageView};
use jpeg_encoder::{ColorType, Encoder, EncodingError, SamplingFactor};
use lambda_runtime::{service_fn, Error, LambdaEvent};
use std::time::Instant;

const SCALE_PERCENT: u32 = 70; // integer math: no float rounding differences
const JPEG_QUALITY: u8 = 75;   // explicit, not the library default
// Chroma subsampling is set explicitly too: the JDK writes 4:2:0 by default and
// image::JpegEncoder cannot be configured, so encoding uses the jpeg-encoder crate.

pub struct Timings {
    pub decode_ms: f64,
    pub resize_ms: f64,
    pub encode_ms: f64,
}

#[tokio::main]
async fn main() -> Result<(), Error> {
    let args: Vec<String> = std::env::args().collect();
    if args.len() == 3 {
        let input = std::fs::read(&args[1])?;
        let (jpeg, t) = process(&input)?;
        std::fs::write(&args[2], &jpeg)?;
        println!(
            "rust  decode={:.2}ms resize={:.2}ms encode={:.2}ms out={} bytes",
            t.decode_ms, t.resize_ms, t.encode_ms, jpeg.len()
        );
        return Ok(());
    }

    let config = aws_config::load_defaults(aws_config::BehaviorVersion::latest()).await;
    let s3 = Client::new(&config);
    let bucket_in = std::env::var("BUCKET_IN")?;
    let bucket_out = std::env::var("BUCKET_OUT")?;
    lambda_runtime::run(service_fn(|event| {
        handle_request(event, &s3, &bucket_in, &bucket_out)
    }))
    .await?;
    Ok(())
}

async fn handle_request(
    event: LambdaEvent<SqsEvent>,
    s3: &Client,
    bucket_in: &str,
    bucket_out: &str,
) -> Result<(), Error> {
    for record in event.payload.records {
        let filename = record.body.ok_or("SQS message has no body")?;
        let input = s3
            .get_object()
            .bucket(bucket_in)
            .key(&filename)
            .send()
            .await?
            .body
            .collect()
            .await?
            .into_bytes();
        let (jpeg, timings) = process(&input)?;
        s3.put_object()
            .bucket(bucket_out)
            .key(format!("Rust_lambda_{filename}"))
            .content_type("image/jpeg")
            .body(ByteStream::from(jpeg))
            .send()
            .await?;
        println!(
            "Processed: {filename} decode={:.2}ms resize={:.2}ms encode={:.2}ms",
            timings.decode_ms, timings.resize_ms, timings.encode_ms
        );
    }
    Ok(())
}

pub fn process(input: &[u8]) -> Result<(Vec<u8>, Timings), Error> {
    let t0 = Instant::now();
    let src = image::load_from_memory(input)?;
    let t1 = Instant::now();

    let (w, h) = src.dimensions();
    let resized = resize(&src, w * SCALE_PERCENT / 100, h * SCALE_PERCENT / 100);
    let t2 = Instant::now();

    let jpeg = encode_jpeg(&resized, JPEG_QUALITY)?;
    let t3 = Instant::now();

    let ms = |a: Instant, b: Instant| b.duration_since(a).as_secs_f64() * 1000.0;
    Ok((jpeg, Timings { decode_ms: ms(t0, t1), resize_ms: ms(t1, t2), encode_ms: ms(t2, t3) }))
}

fn resize(img: &DynamicImage, w: u32, h: u32) -> DynamicImage {
    // resize_exact: same output dimensions as the Java side (no aspect-ratio fitting)
    img.resize_exact(w, h, FilterType::Triangle)
}

fn encode_jpeg(img: &DynamicImage, quality: u8) -> Result<Vec<u8>, EncodingError> {
    let rgb = img.to_rgb8();
    let mut buf = Vec::new();
    let mut enc = Encoder::new(&mut buf, quality);
    enc.set_sampling_factor(SamplingFactor::R_4_2_0);
    enc.encode(rgb.as_raw(), rgb.width() as u16, rgb.height() as u16, ColorType::Rgb)?;
    Ok(buf)
}

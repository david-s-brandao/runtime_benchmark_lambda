use aws_lambda_events::event::sqs::SqsEvent;
use aws_sdk_s3::{primitives::ByteStream, Client};
use image::{imageops::FilterType, DynamicImage, GenericImageView};
use jpeg_encoder::{ColorType, Encoder, EncodingError, SamplingFactor};
use lambda_runtime::{service_fn, Error, LambdaEvent};
use std::io::Read;
use std::net::UdpSocket;
use std::path::Path;
use std::time::{Instant, SystemTime, UNIX_EPOCH};

const SCALE_PERCENT: u32 = 70; // integer math: no float rounding differences
const JPEG_QUALITY: u8 = 75; // explicit, not the library default
                             // Chroma subsampling is set explicitly too: the JDK writes 4:2:0 by default and
                             // image::JpegEncoder cannot be configured, so encoding uses the jpeg-encoder crate.

pub struct Timings {
    pub decode_ms: f64,
    pub resize_ms: f64,
    pub encode_ms: f64,
}

// The Lambda runtime supplies a new X-Ray header for each invocation. Emit
// subsegments under its parent ID; tracing is best-effort and never fails work.
struct XRayTrace {
    root: String,
    parent: String,
    socket: UdpSocket,
    address: String,
}

impl XRayTrace {
    fn from_header(header: Option<&str>) -> Option<Self> {
        let header = header?;
        let field = |prefix| {
            header
                .split(';')
                .find_map(|part| part.trim().strip_prefix(prefix))
        };
        if field("Sampled=") != Some("1") {
            return None;
        }
        let root = field("Root=")?;
        let parent = field("Parent=")?;
        if root.len() != 35
            || !root.starts_with("1-")
            || !root[2..]
                .bytes()
                .all(|b| b == b'-' || b.is_ascii_hexdigit())
            || parent.len() != 16
            || !parent.bytes().all(|b| b.is_ascii_hexdigit())
        {
            return None;
        }
        let socket = UdpSocket::bind("0.0.0.0:0").ok()?;
        let configured = std::env::var("AWS_XRAY_DAEMON_ADDRESS")
            .unwrap_or_else(|_| "127.0.0.1:2000".to_owned());
        let address = configured
            .split(',')
            .find_map(|part| part.trim().strip_prefix("udp:"))
            .unwrap_or(configured.as_str())
            .to_owned();
        Some(Self {
            root: root.to_owned(),
            parent: parent.to_owned(),
            socket,
            address,
        })
    }

    fn finish(&self, name: &str, start: SystemTime) {
        let mut id = [0u8; 8];
        if std::fs::File::open("/dev/urandom")
            .and_then(|mut file| file.read_exact(&mut id))
            .is_err()
        {
            return;
        }
        let timestamp = |time: SystemTime| {
            time.duration_since(UNIX_EPOCH)
                .ok()
                .map(|duration| duration.as_secs_f64())
        };
        let (Some(begin), Some(end)) = (timestamp(start), timestamp(SystemTime::now())) else {
            return;
        };
        // Only fixed phase names are passed in; IDs come from validated Lambda headers.
        let document = format!(
            "{{\"trace_id\":\"{}\",\"id\":\"{}\",\"parent_id\":\"{}\",\"name\":\"{}\",\"type\":\"subsegment\",\"start_time\":{},\"end_time\":{}}}",
            self.root, id.iter().map(|byte| format!("{byte:02x}")).collect::<String>(),
            self.parent, name, begin, end
        );
        let packet = format!("{{\"format\":\"json\",\"version\":1}}\n{document}");
        let _ = self.socket.send_to(packet.as_bytes(), &self.address);
    }
}

fn finish_phase(trace: Option<&XRayTrace>, name: &str, start: SystemTime) {
    if let Some(trace) = trace {
        trace.finish(name, start);
    }
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
            t.decode_ms,
            t.resize_ms,
            t.encode_ms,
            jpeg.len()
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
    let trace = XRayTrace::from_header(event.context.xray_trace_id.as_deref());
    for record in event.payload.records {
        let filename = record.body.ok_or("SQS message has no body")?;
        let start = SystemTime::now();
        let download = async {
            Ok::<_, Error>(
                s3.get_object()
                    .bucket(bucket_in)
                    .key(&filename)
                    .send()
                    .await?
                    .body
                    .collect()
                    .await?
                    .into_bytes(),
            )
        }
        .await;
        finish_phase(trace.as_ref(), "download", start);
        let input = download?;
        let (jpeg, timings) = process_traced(&input, trace.as_ref())?;
        let start = SystemTime::now();
        let upload = s3
            .put_object()
            .bucket(bucket_out)
            .key(format!("Rust_lambda_{}", safe_filename(&filename)?))
            .content_type("image/jpeg")
            .body(ByteStream::from(jpeg))
            .send()
            .await;
        finish_phase(trace.as_ref(), "upload", start);
        upload?;
        println!(
            "Processed: {filename} decode={:.2}ms resize={:.2}ms encode={:.2}ms",
            timings.decode_ms, timings.resize_ms, timings.encode_ms
        );
    }
    Ok(())
}

fn safe_filename(key: &str) -> Result<&str, Error> {
    let name = Path::new(key)
        .file_name()
        .and_then(|name| name.to_str())
        .ok_or("Invalid image key")?;
    if name.is_empty() || name == "." || name == ".." || name.contains('\\') {
        return Err("Invalid image key".into());
    }
    Ok(name)
}

pub fn process(input: &[u8]) -> Result<(Vec<u8>, Timings), Error> {
    process_traced(input, None)
}

fn process_traced(input: &[u8], trace: Option<&XRayTrace>) -> Result<(Vec<u8>, Timings), Error> {
    let t0 = Instant::now();
    let start = SystemTime::now();
    let decoded = image::load_from_memory(input);
    finish_phase(trace, "decode", start);
    let src = decoded?;
    let t1 = Instant::now();

    let (w, h) = src.dimensions();
    let start = SystemTime::now();
    let resized = resize(&src, w * SCALE_PERCENT / 100, h * SCALE_PERCENT / 100);
    finish_phase(trace, "resize", start);
    let t2 = Instant::now();

    let start = SystemTime::now();
    let encoded = encode_jpeg(&resized, JPEG_QUALITY);
    finish_phase(trace, "encode", start);
    let jpeg = encoded?;
    let t3 = Instant::now();

    let ms = |a: Instant, b: Instant| b.duration_since(a).as_secs_f64() * 1000.0;
    Ok((
        jpeg,
        Timings {
            decode_ms: ms(t0, t1),
            resize_ms: ms(t1, t2),
            encode_ms: ms(t2, t3),
        },
    ))
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
    enc.encode(
        rgb.as_raw(),
        rgb.width() as u16,
        rgb.height() as u16,
        ColorType::Rgb,
    )?;
    Ok(buf)
}

#[cfg(test)]
mod tests {
    use super::XRayTrace;

    #[test]
    fn only_sampled_headers_with_valid_parent_ids_emit_subsegments() {
        let header = "Root=1-68dabcde-1234567890abcdef12345678;Parent=0123456789abcdef;Sampled=1";
        assert!(XRayTrace::from_header(Some(header)).is_some());
        assert!(XRayTrace::from_header(Some(&header.replace("Sampled=1", "Sampled=0"))).is_none());
        assert!(XRayTrace::from_header(Some(
            &header.replace("Parent=0123456789abcdef", "Parent=bad")
        ))
        .is_none());
        assert!(XRayTrace::from_header(None).is_none());
    }
}

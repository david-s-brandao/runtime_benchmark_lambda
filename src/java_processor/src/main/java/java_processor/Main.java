package java_processor;

import com.amazonaws.services.lambda.runtime.Context;
import com.amazonaws.services.lambda.runtime.RequestHandler;
import com.amazonaws.services.lambda.runtime.events.SQSEvent;
import com.amazonaws.xray.AWSXRay;
import com.amazonaws.xray.entities.Subsegment;
import software.amazon.awssdk.core.sync.RequestBody;
import software.amazon.awssdk.services.s3.S3Client;
import software.amazon.awssdk.services.s3.model.GetObjectRequest;
import software.amazon.awssdk.services.s3.model.PutObjectRequest;
import javax.imageio.IIOImage;
import javax.imageio.ImageIO;
import javax.imageio.ImageWriteParam;
import javax.imageio.ImageWriter;
import javax.imageio.stream.ImageOutputStream;
import java.awt.Graphics2D;
import java.awt.RenderingHints;
import java.awt.image.BufferedImage;
import java.io.ByteArrayInputStream;
import java.io.ByteArrayOutputStream;
import java.io.IOException;
import java.nio.file.Files;
import java.nio.file.Path;
import java.util.concurrent.Callable;

/**
 * Benchmark workload (Java side). Must stay functionally identical to processor.rs:
 *   decode -> resize to 70% (bilinear, exact dimensions) -> encode JPEG q=75
 * The image processing stays independent of S3 I/O in the Lambda handler.
 */
public final class Main implements RequestHandler<SQSEvent, Void> {
    static final int SCALE_PERCENT = 70;      // integer math: no float rounding differences
    static final float JPEG_QUALITY = 0.75f;  // explicit, not the library default
    private final S3Client s3 = S3Client.create();

    @Override
    public Void handleRequest(SQSEvent event, Context context) {
        String bucketIn = System.getenv("BUCKET_IN");
        String bucketOut = System.getenv("BUCKET_OUT");
        for (SQSEvent.SQSMessage message : event.getRecords()) {
            String filename = message.getBody();
            try {
                long t0 = System.nanoTime();
                byte[] input = traced("download", () -> s3.getObjectAsBytes(GetObjectRequest.builder()
                        .bucket(bucketIn).key(filename).build()).asByteArray());
                long t1 = System.nanoTime();
                Result result = process(input, true);
                long t2 = System.nanoTime();
                traced("upload", () -> s3.putObject(PutObjectRequest.builder()
                        .bucket(bucketOut).key("Java_lambda_" + safeFilename(filename))
                        .contentType("image/jpeg").build(), RequestBody.fromBytes(result.jpeg())));
                long t3 = System.nanoTime();
                context.getLogger().log("Processed: " + filename);
                context.getLogger().log(String.format(java.util.Locale.ROOT,
                        "BenchmarkStages: client_ms=0.00 get_ms=%.2f process_ms=%.2f put_ms=%.2f",
                        (t1 - t0) / 1e6, (t2 - t1) / 1e6, (t3 - t2) / 1e6));
            } catch (Exception e) {
                context.getLogger().log("Error processing " + filename + ": " + e);
                throw new RuntimeException("Failed to process " + filename, e);
            }
        }
        return null;
    }

    public record Timings(double decodeMs, double resizeMs, double encodeMs) {}
    public record Result(byte[] jpeg, Timings timings) {}

    private static <T> T traced(String phase, Callable<T> work) throws Exception {
        Subsegment segment = AWSXRay.beginSubsegment(phase);
        try {
            return work.call();
        } catch (Exception e) {
            segment.addException(e);
            throw e;
        } finally {
            AWSXRay.endSubsegment();
        }
    }

    private interface ImageWork<T> { T run() throws IOException; }

    private static <T> T imagePhase(String phase, boolean trace, ImageWork<T> work) throws IOException {
        if (!trace) return work.run();
        Subsegment segment = AWSXRay.beginSubsegment(phase);
        try {
            return work.run();
        } catch (IOException | RuntimeException e) {
            segment.addException(e);
            throw e;
        } finally {
            AWSXRay.endSubsegment();
        }
    }

    static String safeFilename(String key) {
        String name = Path.of(key).getFileName().toString();
        if (name.isBlank() || name.equals(".") || name.equals("..") || name.contains("\\")) {
            throw new IllegalArgumentException("Invalid image key: " + key);
        }
        return name;
    }

    public static Result process(byte[] input) throws IOException {
        return process(input, false);
    }

    private static Result process(byte[] input, boolean trace) throws IOException {
        long t0 = System.nanoTime();
        BufferedImage src = imagePhase("decode", trace, () -> {
            BufferedImage decoded = ImageIO.read(new ByteArrayInputStream(input));
            if (decoded == null) throw new IOException("Unsupported image format");
            return decoded;
        });
        long t1 = System.nanoTime();

        BufferedImage resized = imagePhase("resize", trace, () -> resize(src,
                src.getWidth() * SCALE_PERCENT / 100,
                src.getHeight() * SCALE_PERCENT / 100));
        long t2 = System.nanoTime();

        byte[] jpeg = imagePhase("encode", trace, () -> encodeJpeg(resized, JPEG_QUALITY));
        long t3 = System.nanoTime();

        return new Result(jpeg, new Timings((t1 - t0) / 1e6, (t2 - t1) / 1e6, (t3 - t2) / 1e6));
    }

    static BufferedImage resize(BufferedImage src, int w, int h) {
        BufferedImage out = new BufferedImage(w, h, BufferedImage.TYPE_INT_RGB);
        Graphics2D g = out.createGraphics();
        g.setRenderingHint(RenderingHints.KEY_INTERPOLATION, RenderingHints.VALUE_INTERPOLATION_BILINEAR);
        g.setRenderingHint(RenderingHints.KEY_RENDERING, RenderingHints.VALUE_RENDER_QUALITY);
        g.drawImage(src, 0, 0, w, h, null);
        g.dispose();
        return out;
    }

    static byte[] encodeJpeg(BufferedImage img, float quality) throws IOException {
        ImageWriter writer = ImageIO.getImageWritersByFormatName("jpeg").next();
        ImageWriteParam param = writer.getDefaultWriteParam();
        param.setCompressionMode(ImageWriteParam.MODE_EXPLICIT);
        param.setCompressionQuality(quality);
        ByteArrayOutputStream baos = new ByteArrayOutputStream();
        try (ImageOutputStream ios = ImageIO.createImageOutputStream(baos)) {
            writer.setOutput(ios);
            writer.write(null, new IIOImage(img, null, null), param);
        } finally {
            writer.dispose();
        }
        return baos.toByteArray();
    }

    /** Local test: java Main in.jpg out.jpg */
    public static void main(String[] args) throws IOException {
        System.setProperty("java.awt.headless", "true");
        byte[] in = Files.readAllBytes(Path.of(args[0]));
        Result r = process(in);
        Files.write(Path.of(args[1]), r.jpeg());
        System.out.printf("java  decode=%.2fms resize=%.2fms encode=%.2fms out=%d bytes%n",
                r.timings().decodeMs(), r.timings().resizeMs(), r.timings().encodeMs(), r.jpeg().length);
    }
}

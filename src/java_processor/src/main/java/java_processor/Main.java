package java_processor;

import com.amazonaws.services.lambda.runtime.Context;
import com.amazonaws.services.lambda.runtime.RequestHandler;
import com.amazonaws.services.lambda.runtime.events.SQSEvent;
import com.amazonaws.xray.AWSXRay;
import com.amazonaws.xray.entities.Segment;
import software.amazon.awssdk.services.s3.S3Client;
import software.amazon.awssdk.services.s3.model.GetObjectRequest;
import software.amazon.awssdk.services.s3.model.PutObjectRequest;
import software.amazon.awssdk.core.sync.RequestBody;
import javax.imageio.ImageIO;
import java.awt.*;
import java.awt.image.BufferedImage;
import java.io.ByteArrayOutputStream;

public class Main implements RequestHandler<SQSEvent, Void> {

    private final S3Client s3 = S3Client.create();
    private final String bucketIn  = System.getenv("BUCKET_IN");
    private final String bucketOut = System.getenv("BUCKET_OUT");

    @Override
    public Void handleRequest(SQSEvent event, Context context) {
        for (SQSEvent.SQSMessage message : event.getRecords()) {
            String filename = message.getBody();
            Segment segment = AWSXRay.beginSegment("java_function");
            try {
                byte[] imageBytes = s3.getObjectAsBytes(
                    GetObjectRequest.builder().bucket(bucketIn).key(filename).build()
                ).asByteArray();

                BufferedImage original = ImageIO.read(new java.io.ByteArrayInputStream(imageBytes));
                BufferedImage compressed = compress(original, 0.7f);

                ByteArrayOutputStream baos = new ByteArrayOutputStream();
                ImageIO.write(compressed, "jpg", baos);

                s3.putObject(
                    PutObjectRequest.builder().bucket(bucketOut).key("Java_lambda_" + filename).build(),
                    RequestBody.fromBytes(baos.toByteArray())
                );

                segment.putAnnotation("filename", filename);
                context.getLogger().log("Processed: " + filename);
            } catch (Exception e) {
                segment.addException(e);
                context.getLogger().log("Error: " + e.getMessage());
                throw new RuntimeException(e);
            } finally {
                AWSXRay.endSegment();
            }
        }
        return null;
    }

    private BufferedImage compress(BufferedImage src, float scale) {
        int w = (int) (src.getWidth() * scale);
        int h = (int) (src.getHeight() * scale);
        BufferedImage out = new BufferedImage(w, h, BufferedImage.TYPE_INT_RGB);
        Graphics2D g = out.createGraphics();
        g.drawImage(src, 0, 0, w, h, null);
        g.dispose();
        return out;
    }
}

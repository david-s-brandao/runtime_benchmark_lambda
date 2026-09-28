package java_processor_snapstart;

import org.junit.jupiter.api.Test;
import javax.imageio.ImageIO;
import java.awt.image.BufferedImage;
import java.io.ByteArrayOutputStream;
import java.io.IOException;
import java.io.ByteArrayInputStream;

import static org.junit.jupiter.api.Assertions.*;

class MainTest {
    @Test
    void processResizesToSeventyPercent() throws IOException {
        BufferedImage input = new BufferedImage(13, 11, BufferedImage.TYPE_INT_RGB);
        ByteArrayOutputStream source = new ByteArrayOutputStream();
        assertTrue(ImageIO.write(input, "jpeg", source));

        Main.Result result = Main.process(source.toByteArray());
        BufferedImage output = ImageIO.read(new ByteArrayInputStream(result.jpeg()));
        assertNotNull(output);
        assertEquals(9, output.getWidth());
        assertEquals(7, output.getHeight());
    }

    @Test
    void processRejectsInvalidImage() {
        assertThrows(IOException.class, () -> Main.process("not an image".getBytes()));
    }
}

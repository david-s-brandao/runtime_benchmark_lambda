def main():
    func("images.md")


def func(filename):
    with open(filename, "w", encoding="utf-8") as file:
        for i in range(101):
            file.write(f"""<!-- Image {i} -->
            ### Image {i}
            <p align="center">
            <img src="/images/original_images/image_{i}.jpg" width="30%" alt="Original 1">
            <br>
            <i>Original</i>
            <p align="center">
                <img src="/images/processed_images/Java_lambda_image_{i}.jpg" width="30%" alt="Java 1">
                <img src="/images/processed_images/Rust_lambda_image_{i}.jpg" width="30%" alt="Rust 1">
                <img src="/images/processed_images/Java_snapstart_lambda_image_{i}.jpg" width="30%" alt="Rust 1">
            <p>

            <br>
            <p align="center">
                <i>Java 21 &nbsp;&nbsp;|&nbsp;&nbsp; Rust&nbsp;&nbsp;|&nbsp;&nbsp; Java 21 + Snapstart</i>
            </p>
            </p>

            ---
        """)


if __name__ == "__main__":
    main()

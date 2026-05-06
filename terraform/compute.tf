resource "aws_lambda_function" "java_lambda" {
    role = aws_iam_role.processor_role.arn
    function_name = "java_function"
    filename = "../src/java_processor/target/app.jar"
    source_code_hash = filebase64sha256("../src/java_processor/target/app.jar")
    handler = "java_processor.Main::handleRequest"
    runtime = "java21"
    timeout = 30
    memory_size = 512
    tracing_config {
        mode = "Active"
    }
    environment {
        variables = {
            BUCKET_IN  = aws_s3_bucket.images_in_bucket.bucket
            BUCKET_OUT = aws_s3_bucket.images_out_bucket.bucket
        }
    }
}

resource "aws_lambda_function" "rust_lambda" {
    role = aws_iam_role.processor_role.arn
    function_name = "rust_function"
    filename = "../src/rust_processor/bootstrap.zip"
    source_code_hash = filebase64sha256("../src/rust_processor/bootstrap.zip")
    handler = "bootstrap"
    runtime = "provided.al2023"
    timeout = 30
    memory_size = 512
    tracing_config {
        mode = "Active"
    }
    environment {
        variables = {
            BUCKET_IN  = aws_s3_bucket.images_in_bucket.bucket
            BUCKET_OUT = aws_s3_bucket.images_out_bucket.bucket
        }
    }
}


resource "aws_lambda_function" "noti_lambda" {
    role = aws_iam_role.noti_role.arn
    function_name = "noti_lambda"
    filename = "../scripts/producer.zip"
    source_code_hash = filebase64sha256("../scripts/producer.zip")
    handler = "producer.handler"
    runtime = "python3.12"
    timeout = 60
    environment {
        variables = {
            BUCKET_IN     = aws_s3_bucket.images_in_bucket.bucket
            BUCKET_OUT    = aws_s3_bucket.images_out_bucket.bucket
            SNS_TOPIC_ARN = aws_sns_topic.image_notifications.arn
        }
    }
}


resource "aws_lambda_function" "logs_lambda" {
    role = aws_iam_role.logs_role.arn
    function_name = "logs_lambda"
    filename = "../scripts/analyzer.zip"
    source_code_hash = filebase64sha256("../scripts/analyzer.zip")
    handler = "analyzer.handler"
    runtime = "python3.12"
    timeout = 60
    environment {
        variables = {
            LOGS_BUCKET = aws_s3_bucket.logs_bucket.bucket
        }
    }
}

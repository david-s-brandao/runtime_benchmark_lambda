resource "aws_sqs_queue" "sqs_java" {
    name = "sqs_java"
    visibility_timeout_seconds = 180
    redrive_policy = jsonencode({
        deadLetterTargetArn = aws_sqs_queue.dlq_java.arn
        maxReceiveCount     = 5
    })
}
resource "aws_sqs_queue" "sqs_rust" {
    name = "sqs_rust"
    visibility_timeout_seconds = 180
    redrive_policy = jsonencode({
        deadLetterTargetArn = aws_sqs_queue.dlq_rust.arn
        maxReceiveCount     = 5
    })
}
resource "aws_sqs_queue" "sqs_java_snapstart" {
    name = "sqs_java_snapstart"
    visibility_timeout_seconds = 180
    redrive_policy = jsonencode({
        deadLetterTargetArn = aws_sqs_queue.dlq_java_snapstart.arn
        maxReceiveCount     = 5
    })
}
resource "aws_sqs_queue" "dlq_java" {
    name                      = "sqs_java_dlq"
    message_retention_seconds = 1209600
}
resource "aws_sqs_queue" "dlq_rust" {
    name                      = "sqs_rust_dlq"
    message_retention_seconds = 1209600
}
resource "aws_sqs_queue" "dlq_java_snapstart" {
    name                      = "sqs_java_snapstart_dlq"
    message_retention_seconds = 1209600
}
resource "aws_sns_topic" "image_notifications" {
    name = "image_notifications"
}
resource "aws_sns_topic_subscription" "sub_sqs_java" {
    topic_arn            = aws_sns_topic.image_notifications.arn
    protocol             = "sqs"
    endpoint             = aws_sqs_queue.sqs_java.arn
    raw_message_delivery = true
}
resource "aws_sns_topic_subscription" "sub_sqs_rust" {
    topic_arn            = aws_sns_topic.image_notifications.arn
    protocol             = "sqs"
    endpoint             = aws_sqs_queue.sqs_rust.arn
    raw_message_delivery = true
}
resource "aws_sns_topic_subscription" "sub_sqs_java_snapstart" {
    topic_arn            = aws_sns_topic.image_notifications.arn
    protocol             = "sqs"
    endpoint             = aws_sqs_queue.sqs_java_snapstart.arn
    raw_message_delivery = true
}
    
resource "aws_sqs_queue_policy" "policy_sqs_java" {
    queue_url = aws_sqs_queue.sqs_java.id
    policy = jsonencode({
        Version = "2012-10-17"
        Statement = [
            {
                Effect = "Allow"
                Principal = "*"
                Action = "SQS:SendMessage"
                Resource = aws_sqs_queue.sqs_java.arn
                Condition = {
                    ArnEquals = {
                        "aws:SourceArn" = aws_sns_topic.image_notifications.arn
                    }
                }
            }
        ]
    })
}

resource "aws_sqs_queue_policy" "policy_sqs_rust" {
    queue_url = aws_sqs_queue.sqs_rust.id
    policy = jsonencode({
        Version = "2012-10-17"
        Statement = [
            {
                Effect = "Allow"
                Principal = "*"
                Action = "SQS:SendMessage"
                Resource = aws_sqs_queue.sqs_rust.arn
                Condition = {
                    ArnEquals = {
                        "aws:SourceArn" = aws_sns_topic.image_notifications.arn
                    }
                }
            }
        ]
    })
}

resource "aws_sqs_queue_policy" "policy_sqs_java_snapstart" {
    queue_url = aws_sqs_queue.sqs_java_snapstart.id
    policy = jsonencode({
        Version = "2012-10-17"
        Statement = [
            {
                Effect = "Allow"
                Principal = "*"
                Action = "SQS:SendMessage"
                Resource = aws_sqs_queue.sqs_java_snapstart.arn
                Condition = {
                    ArnEquals = {
                        "aws:SourceArn" = aws_sns_topic.image_notifications.arn
                    }
                }
            }
        ]
    })
}

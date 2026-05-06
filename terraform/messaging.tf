resource "aws_sqs_queue" "sqs_java" {
    name = "sqs_java"
}
resource "aws_sqs_queue" "sqs_rust" {
    name = "sqs_rust"
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
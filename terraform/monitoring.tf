resource "aws_cloudwatch_event_rule" "logs_schedule" {
  schedule_expression = "cron(0 23 * * ? *)"
}

resource "aws_cloudwatch_event_target" "logs_target" {
  rule = aws_cloudwatch_event_rule.logs_schedule.name
  arn  = aws_lambda_function.logs_lambda.arn
}

resource "aws_lambda_permission" "allow_eventbridge" {
  action        = "lambda:InvokeFunction"
  function_name = aws_lambda_function.logs_lambda.function_name
  principal     = "events.amazonaws.com"
  source_arn    = aws_cloudwatch_event_rule.logs_schedule.arn
}

# Trigger noti_lambda every minute, only between 07:00 and 23:00 UTC (Mon-Sun)
resource "aws_cloudwatch_event_rule" "noti_schedule" {
  schedule_expression = "cron(0/30 * * * ? *)"
  description         = "Trigger noti_lambda every minute during daytime (07:00-23:00 UTC)"
}

resource "aws_cloudwatch_event_target" "noti_target" {
  rule = aws_cloudwatch_event_rule.noti_schedule.name
  arn  = aws_lambda_function.noti_lambda.arn
}

resource "aws_lambda_permission" "allow_eventbridge_noti" {
  action        = "lambda:InvokeFunction"
  function_name = aws_lambda_function.noti_lambda.function_name
  principal     = "events.amazonaws.com"
  source_arn    = aws_cloudwatch_event_rule.noti_schedule.arn
}

# SQS triggers for java and rust processors
resource "aws_lambda_event_source_mapping" "sqs_java_trigger" {
  event_source_arn = aws_sqs_queue.sqs_java.arn
  function_name    = aws_lambda_function.java_lambda.arn
  batch_size       = 1
  scaling_config {
    maximum_concurrency = 100
  }
}

resource "aws_lambda_event_source_mapping" "sqs_rust_trigger" {
  event_source_arn = aws_sqs_queue.sqs_rust.arn
  function_name    = aws_lambda_function.rust_lambda.arn
  batch_size       = 1
  scaling_config {
    maximum_concurrency = 100
  }
}

resource "aws_xray_sampling_rule" "java_high_sampling" {
  rule_name      = "java-high-sampling"
  priority       = 50
  fixed_rate     = 1.0
  reservoir_size = 100
  service_name   = "java_function"
  service_type   = "AWS::Lambda::Function"
  host           = "*"
  http_method    = "*"
  url_path       = "*"
  resource_arn   = "arn:aws:lambda:us-east-1:586710034156:function:java_function"
  version        = 1
}

resource "aws_xray_sampling_rule" "rust_high_sampling" {
  rule_name      = "rust-high-sampling"
  priority       = 51
  fixed_rate     = 1.0
  reservoir_size = 100
  service_name   = "rust_function"
  service_type   = "AWS::Lambda::Function"
  host           = "*"
  http_method    = "*"
  url_path       = "*"
  resource_arn   = "arn:aws:lambda:us-east-1:586710034156:function:rust_function"
  version        = 1
}

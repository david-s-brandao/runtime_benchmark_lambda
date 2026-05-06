resource "aws_s3_bucket" "images_in_bucket" {
  bucket = var.bucket_input
  force_destroy = true
  tags = {
    Name = "Image base bucket"
    Environment = "Dev"
  }
}

resource "aws_s3_bucket" "images_out_bucket" {
  bucket = var.bucket_output
  force_destroy = true
  tags = {
    Name = "Image output bucket"
    Environment = "Dev"
  }
}

resource "aws_s3_bucket" "logs_bucket" {
  bucket = var.bucket_logs
  force_destroy = true
  tags = {
    Name = "Lambda logs bucket"
    Environment = "Dev"
  }
}



resource "aws_s3_bucket_lifecycle_configuration" "short-life-images" {
    bucket = aws_s3_bucket.images_out_bucket.id
    rule {
      id     = "short-life-images"
      status = "Enabled"
      expiration {
        days = 1
      }
    }
}

resource "aws_s3_bucket_lifecycle_configuration" "short-life-logs" {
    bucket = aws_s3_bucket.logs_bucket.id
    rule {
        id     = "short-life-logs"
        status = "Enabled"
        expiration {
            days = 2
        }
    }
}
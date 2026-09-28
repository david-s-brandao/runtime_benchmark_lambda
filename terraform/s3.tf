resource "aws_s3_bucket" "images_in_bucket" {
  bucket = "s3-input-benchmark"
  force_destroy = true
  tags = {
    Name = "Image base bucket"
    Environment = "Dev"
  }
}

resource "aws_s3_bucket" "images_out_bucket" {
  bucket = "s3-output-benchmark"
  force_destroy = true
  tags = {
    Name = "Image output bucket"
    Environment = "Dev"
  }
}

resource "aws_s3_bucket" "logs_bucket" {
  bucket = "s3-logs-benchmark"
  force_destroy = true
  tags = {
    Name = "Lambda logs bucket"
    Environment = "Dev"
  }
}



resource "aws_s3_bucket_lifecycle_configuration" "short-life-images-benchmark" {
    bucket = aws_s3_bucket.images_out_bucket.id
    rule {
      id     = "short-life-images-benchmark"
      status = "Enabled"
      expiration {
        days = 1
      }
    }
}

resource "aws_s3_bucket_lifecycle_configuration" "short-life-logs-benchmark" {
    bucket = aws_s3_bucket.logs_bucket.id
    rule {
        id     = "short-life-logs-benchmark"
        status = "Enabled"
        expiration {
            days = 2
        }
    }
}
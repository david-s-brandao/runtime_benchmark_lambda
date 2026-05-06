variable "bucket_input" {
  description = "Name of the S3 bucket for input images"
  type        = string
}

variable "bucket_output" {
  description = "Name of the S3 bucket for output images"
  type        = string
}

variable "bucket_logs" {
  description = "Name of the S3 bucket for Lambda logs"
  type        = string
}

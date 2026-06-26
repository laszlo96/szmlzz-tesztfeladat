variable "aws_region" {
  default = "eu-central-1"
}

variable "cluster_name" {
  type = string
}

variable "environment" {
  type = string
}

variable "vpc_cidr" {
  default = "10.0.0.0/16"
}

variable "availability_zones" {
  type    = list(string)
  default = ["eu-central-1a", "eu-central-1b", "eu-central-1c"]
}

variable "aws_region" {
  default = "eu-central-1"
}

variable "cluster_name" {
  type = string
}

variable "environment" {
  type = string
}

variable "kubernetes_version" {
  default = "1.29"
}

variable "private_subnet_ids" {
  type = list(string)
}

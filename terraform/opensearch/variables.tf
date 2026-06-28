variable "aws_region" {
  default = "eu-central-1"
}

variable "environment" {
  type = string
}

variable "vpc_id" {
  type = string
}

variable "private_subnet_ids" {
  type = list(string)
}

variable "eks_node_security_group_id" {
  type        = string
  description = "EKS node group security group ID"
}

variable "oidc_provider_arn" {
  type        = string
  description = "EKS OIDC provider ARN (az eks modulból)"
}

variable "oidc_provider" {
  type        = string
  description = "EKS OIDC provider URL https:// nélkül"
}

variable "instance_type" {
  default     = "t3.medium.search"
  description = "Prod-on r6g.large.search ajánlott, dev-en t3.medium.search elég"
}

variable "instance_count" {
  default     = 1
  description = "Prod-on minimum 3 (multi-AZ), dev/uat-on 1"
}

variable "volume_size_gb" {
  default = 100
}

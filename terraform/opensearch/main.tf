terraform {
  required_providers {
    aws = {
      source  = "hashicorp/aws"
      version = "~> 5.0"
    }
  }
}

provider "aws" {
  region = var.aws_region
}

locals {
  domain_name = "monitoring-${var.environment}"
}

data "aws_caller_identity" "current" {}

resource "aws_security_group" "opensearch" {
  name        = "${local.domain_name}-sg"
  description = "OpenSearch cluster access"
  vpc_id      = var.vpc_id

  ingress {
    from_port          = 443
    to_port            = 443
    protocol           = "tcp"
    security_group_ids = [var.eks_node_security_group_id]
    description        = "EKS nodes"
  }

  egress {
    from_port   = 0
    to_port     = 0
    protocol    = "-1"
    cidr_blocks = ["0.0.0.0/0"]
  }

  tags = {
    Name        = "${local.domain_name}-sg"
    Environment = var.environment
  }
}

resource "aws_opensearch_domain" "main" {
  domain_name    = local.domain_name
  engine_version = "OpenSearch_2.11"

  cluster_config {
    instance_type          = var.instance_type
    instance_count         = var.instance_count
    zone_awareness_enabled = var.instance_count > 1

    dynamic "zone_awareness_config" {
      for_each = var.instance_count > 1 ? [1] : []
      content {
        availability_zone_count = min(var.instance_count, 3)
      }
    }
  }

  ebs_options {
    ebs_enabled = true
    volume_type = "gp3"
    volume_size = var.volume_size_gb
    throughput  = 250
  }

  vpc_options {
    subnet_ids         = var.private_subnet_ids
    security_group_ids = [aws_security_group.opensearch.id]
  }

  encrypt_at_rest {
    enabled = true
  }

  node_to_node_encryption {
    enabled = true
  }

  domain_endpoint_options {
    enforce_https       = true
    tls_security_policy = "Policy-Min-TLS-1-2-2019-07"
  }

  advanced_security_options {
    enabled                        = true
    anonymous_auth_enabled         = false
    internal_user_database_enabled = false

    master_user_options {
      master_user_arn = aws_iam_role.opensearch_admin.arn
    }
  }

  log_publishing_options {
    cloudwatch_log_group_arn = aws_cloudwatch_log_group.opensearch_slow.arn
    log_type                 = "INDEX_SLOW_LOGS"
  }

  tags = {
    Environment = var.environment
  }
}

data "aws_iam_policy_document" "opensearch_access" {
  statement {
    effect = "Allow"
    principals {
      type        = "AWS"
      identifiers = [aws_iam_role.opensearch_admin.arn]
    }
    actions   = ["es:*"]
    resources = ["${aws_opensearch_domain.main.arn}/*"]
  }

  statement {
    effect = "Allow"
    principals {
      type        = "AWS"
      identifiers = [aws_iam_role.otel_collector.arn]
    }
    actions = [
      "es:ESHttpPost",
      "es:ESHttpPut",
      "es:ESHttpGet",
    ]
    resources = ["${aws_opensearch_domain.main.arn}/*"]
  }

  statement {
    effect = "Allow"
    principals {
      type        = "AWS"
      identifiers = [aws_iam_role.mcp_server.arn]
    }
    actions   = ["es:ESHttpGet", "es:ESHttpPost"]
    resources = ["${aws_opensearch_domain.main.arn}/*"]
  }
}

resource "aws_opensearch_domain_policy" "main" {
  domain_name     = aws_opensearch_domain.main.domain_name
  access_policies = data.aws_iam_policy_document.opensearch_access.json
}

resource "aws_cloudwatch_log_group" "opensearch_slow" {
  name              = "/aws/opensearch/${local.domain_name}/index-slow"
  retention_in_days = 7
}

# --- IAM roles ---

data "aws_iam_policy_document" "opensearch_admin_assume" {
  statement {
    actions = ["sts:AssumeRole"]
    principals {
      type        = "AWS"
      identifiers = ["arn:aws:iam::${data.aws_caller_identity.current.account_id}:root"]
    }
  }
}

resource "aws_iam_role" "opensearch_admin" {
  name               = "${local.domain_name}-admin"
  assume_role_policy = data.aws_iam_policy_document.opensearch_admin_assume.json
}

# IRSA – OTel Collector (írás)
data "aws_iam_policy_document" "otel_collector_assume" {
  statement {
    actions = ["sts:AssumeRoleWithWebIdentity"]
    principals {
      type        = "Federated"
      identifiers = [var.oidc_provider_arn]
    }
    condition {
      test     = "StringEquals"
      variable = "${var.oidc_provider}:sub"
      values   = ["system:serviceaccount:monitoring:otel-collector"]
    }
  }
}

resource "aws_iam_role" "otel_collector" {
  name               = "otel-collector-${var.environment}"
  assume_role_policy = data.aws_iam_policy_document.otel_collector_assume.json
}

# IRSA – MCP server (olvasás)
data "aws_iam_policy_document" "mcp_server_assume" {
  statement {
    actions = ["sts:AssumeRoleWithWebIdentity"]
    principals {
      type        = "Federated"
      identifiers = [var.oidc_provider_arn]
    }
    condition {
      test     = "StringEquals"
      variable = "${var.oidc_provider}:sub"
      values   = ["system:serviceaccount:mcp-server:mcp-server"]
    }
  }
}

resource "aws_iam_role" "mcp_server" {
  name               = "mcp-server-${var.environment}"
  assume_role_policy = data.aws_iam_policy_document.mcp_server_assume.json
}

# SNS topic riasztásokhoz (OpenSearch Alerting plugin küldi)
resource "aws_sns_topic" "alerts" {
  name = "monitoring-alerts-${var.environment}"
}

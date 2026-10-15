# Lets GitHub Actions get short-lived AWS credentials without any stored access keys.
# Only workflows running on the main branch of github_owner/github_repo can assume the role.

resource "aws_iam_openid_connect_provider" "github" {
  url            = "https://token.actions.githubusercontent.com"
  client_id_list = ["sts.amazonaws.com"]

  # AWS no longer checks these for GitHub, but older provider versions require a value.
  thumbprint_list = [
    "6938fd4d98bab03faadb97b34396831e3780aea1",
    "1c58a3a8518e8759bf075b76b750d4f2df264fcd",
  ]
}

data "aws_iam_policy_document" "github_trust" {
  statement {
    actions = ["sts:AssumeRoleWithWebIdentity"]

    principals {
      type        = "Federated"
      identifiers = [aws_iam_openid_connect_provider.github.arn]
    }

    condition {
      test     = "StringEquals"
      variable = "token.actions.githubusercontent.com:aud"
      values   = ["sts.amazonaws.com"]
    }

    condition {
      test     = "StringEquals"
      variable = "token.actions.githubusercontent.com:sub"
      values = [
        # Newer GitHub format, with immutable owner and repo IDs
        "repo:${var.github_owner}@172268738/${var.github_repo}@1420551244:ref:refs/heads/main",
        # Older format, kept in case GitHub sends it
        "repo:${var.github_owner}/${var.github_repo}:ref:refs/heads/main",
      ]
    }
  }
}

resource "aws_iam_role" "github_deploy" {
  name                 = "github-actions-deploy"
  description          = "Assumed by GitHub Actions in ${var.github_owner}/${var.github_repo} (main branch only)"
  assume_role_policy   = data.aws_iam_policy_document.github_trust.json
  max_session_duration = 3600
}

# Broad permissions for now; the trust policy above limits who can use the role.
# Tighten this once the set of services used is settled.
resource "aws_iam_role_policy_attachment" "github_deploy_admin" {
  role       = aws_iam_role.github_deploy.name
  policy_arn = "arn:aws:iam::aws:policy/AdministratorAccess"
}

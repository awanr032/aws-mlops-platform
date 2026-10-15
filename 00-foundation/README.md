# 00 · Foundation

The account baseline every other project in this repo relies on. Unlike the later projects, this one stays deployed.

## What it creates

| Resource | Why |
|---|---|
| Private, encrypted, versioned S3 bucket | Stores audit logs; old logs expire automatically |
| CloudTrail (all regions) | Records every API call in the account |
| Monthly cost budget with email alerts | Warns at 50% and 85% of actual spend, and if spend is forecast to exceed the limit |
| GitHub OIDC provider + `github-actions-deploy` role | GitHub Actions gets short-lived credentials; no access keys stored anywhere |

## Manual steps done before this (console)

- MFA on the root user; root has no access keys
- Everyday IAM admin user with MFA and no access keys
- Old deploy user's console access disabled and access key deactivated

## Deploy (from AWS CloudShell, region eu-west-2)

```bash
cd 00-foundation
cp terraform.tfvars.example terraform.tfvars   # then edit your email
terraform init
terraform plan
terraform apply
```

Then in GitHub: **Settings → Secrets and variables → Actions → Variables → New repository variable**,
name `AWS_DEPLOY_ROLE_ARN`, value = the `github_deploy_role_arn` output.
Run **Actions → foundation-check → Run workflow**; it should print the `github-actions-deploy` role.

## Teardown

`terraform destroy`. Empty the logs bucket first (it is versioned), or the destroy will stop at the bucket.

## Cost

| Item | Approx. monthly cost |
|---|---|
| CloudTrail (first management-event trail) | Free |
| S3 log storage | A few pence |
| Budgets (first two) | Free |
| IAM / OIDC | Free |

Actual cost on my bill: _fill in_

## What went wrong and how I fixed it

_Fill in. For example: `aws login` failing for the IAM user, and what turned out to be the cause._

## Notes

- The deploy role currently has `AdministratorAccess`, limited by its trust policy to this repo's `main` branch. It will be tightened once the later projects settle which services they use.
- Terraform state for this folder is local. Keep a copy of `terraform.tfstate` somewhere safe (not in git).

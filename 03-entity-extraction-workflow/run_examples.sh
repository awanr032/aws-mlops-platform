#!/usr/bin/env bash
# Run every example work order through the deployed workflow and print the outcome.
# Usage (Git Bash, from this folder, after `aws login` and `terraform init`):
#   bash run_examples.sh
set -euo pipefail

ARN=$(terraform output -raw state_machine_arn)
TABLE=$(terraform output -raw table_name)

for file in examples/*.json; do
  name="run-$(basename "$file" .json)-$(date +%s)"
  exec_arn=$(aws stepfunctions start-execution \
    --state-machine-arn "$ARN" --name "$name" \
    --input "file://$file" --query executionArn --output text)

  status=RUNNING
  while [ "$status" = "RUNNING" ]; do
    sleep 2
    status=$(aws stepfunctions describe-execution --execution-arn "$exec_arn" --query status --output text)
  done
  printf '%-32s %s\n' "$(basename "$file")" "$status"
done

echo
echo "Results table ($TABLE):"
aws dynamodb scan --table-name "$TABLE" \
  --query "Items[].[work_order_id.S, status.S, entities.S || problems.S || error.S]" \
  --output table

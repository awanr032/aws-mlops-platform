# The model registry: a catalogue of every trained version with its metrics and approval status.
# Terraform creates the empty group; the pipeline adds a version after each training run.
resource "aws_sagemaker_model_package_group" "bearing" {
  model_package_group_name        = var.model_group_name
  model_package_group_description = "Bearing fault classifier. Batch scoring always uses the newest Approved version."
}

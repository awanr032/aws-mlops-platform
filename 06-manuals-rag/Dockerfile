# One image, two Lambda functions: the question API (default command) and the indexer
# (Terraform overrides the command with indexer.handler). FAISS needs compiled libraries,
# which is why this project uses a container image, as in project 04.
FROM public.ecr.aws/lambda/python:3.13

# boto3 is already in AWS's Lambda base image; we add FAISS and NumPy.
COPY requirements.txt ${LAMBDA_TASK_ROOT}/
RUN pip install --no-cache-dir -r ${LAMBDA_TASK_ROOT}/requirements.txt

COPY rag/ ${LAMBDA_TASK_ROOT}/

CMD ["query.handler"]

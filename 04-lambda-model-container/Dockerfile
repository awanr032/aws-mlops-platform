# Two stages: train the model, then build the small image Lambda actually runs.
# Both stages use AWS's official Lambda Python base image, so the model is trained
# and served with identical Python and library versions.

# ---- Stage 1: train and apply the quality gate -----------------------------
FROM public.ecr.aws/lambda/python:3.13 AS train

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY training/ training/
ARG MIN_ACCURACY=0.90
# If the model is not good enough, this command fails and so does the whole build:
# nothing is pushed and the running Lambda keeps the previous, approved model.
RUN python training/train.py --out /model --min-accuracy ${MIN_ACCURACY}

# ---- Stage 2: the image Lambda runs -----------------------------------------
FROM public.ecr.aws/lambda/python:3.13

COPY requirements.txt ${LAMBDA_TASK_ROOT}/
RUN pip install --no-cache-dir -r ${LAMBDA_TASK_ROOT}/requirements.txt

COPY app/ ${LAMBDA_TASK_ROOT}/
COPY --from=train /model ${LAMBDA_TASK_ROOT}/model

CMD ["handler.lambda_handler"]

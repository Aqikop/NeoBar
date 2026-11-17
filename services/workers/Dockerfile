FROM python:3.11-slim

ARG WITH_ML=false
WORKDIR /app

RUN apt-get update && apt-get install -y --no-install-recommends curl \
    && rm -rf /var/lib/apt/lists/*

COPY services/workers/requirements.txt services/workers/requirements-ml.txt ./
RUN pip install --no-cache-dir -r requirements.txt \
    && if [ "$WITH_ML" = "true" ]; then pip install --no-cache-dir -r requirements-ml.txt; fi

COPY shared/neobar_common ./neobar_common
COPY services/workers/src ./src

CMD ["python", "-m", "src.main"]
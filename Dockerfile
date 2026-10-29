FROM python:3.12-slim
ENV PYTHONUNBUFFERED=1 PYTHONDONTWRITEBYTECODE=1 HOST=0.0.0.0 PORT=10000
RUN apt-get update && apt-get install -y --no-install-recommends tesseract-ocr && rm -rf /var/lib/apt/lists/*
WORKDIR /app
COPY requirements-deploy.txt /app/
RUN pip install --no-cache-dir -r requirements-deploy.txt
COPY . /app/
RUN python -c "from core.nlp_engine import train_and_save_model; train_and_save_model()"
EXPOSE 10000
CMD ["python","-m","village.server"]

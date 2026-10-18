FROM python:3.11-slim

ENV PYTHONDONTWRITEBYTECODE=1 PYTHONUNBUFFERED=1

# git: dbt deps instala audit_helper desde un repo git
RUN apt-get update && apt-get install -y --no-install-recommends git && rm -rf /var/lib/apt/lists/*

WORKDIR /app
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY . .
RUN chmod +x scripts/docker-entrypoint.sh

EXPOSE 8501
ENTRYPOINT ["scripts/docker-entrypoint.sh"]
CMD ["streamlit", "run", "src/ui/app.py", "--server.address=0.0.0.0", "--server.port=8501"]

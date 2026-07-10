# Piano Companion analysis service
# Build:  docker build -t piano-companion-api ./server
# Run:    docker run -p 8756:8756 -e PORT=8756 piano-companion-api
# Works as-is on Render / Railway / Fly.io (they inject PORT).
FROM python:3.11-slim

RUN apt-get update \
 && apt-get install -y --no-install-recommends ffmpeg \
 && rm -rf /var/lib/apt/lists/*

WORKDIR /app
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY . .

ENV PORT=8756
EXPOSE 8756
CMD ["python", "main.py"]

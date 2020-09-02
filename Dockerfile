FROM python:3.8-slim
RUN apt-get update && \
    apt-get install -y --no-install-recommends build-essential libffi-dev libxml2 libxml2-dev && \
    apt-get clean && rm -rf /var/lib/apt/lists/*
COPY ./requirements.txt /app/requirements.txt
RUN pip install --no-cache-dir -r /app/requirements.txt
COPY ./ /app
WORKDIR "/app"
ENTRYPOINT [ "/usr/local/bin/python", "-u", "./main.py" ]
FROM python:3.8-alpine
RUN apk add --no-cache build-base libffi-dev opus ffmpeg
COPY ./requirements.txt /app/requirements.txt
RUN pip install --no-cache-dir -r /app/requirements.txt
COPY ./ /app
WORKDIR "/app"
ENTRYPOINT [ "/usr/local/bin/python", "-u", "./main.py" ]
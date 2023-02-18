FROM python:3.10-alpine

WORKDIR /home

COPY aa_greeting.py ./
COPY requirements.txt ./

RUN pip install --no-cache-dir -U pip && \
    pip install --no-cache-dir -r requirements.txt && \
    chmod +x aa_greeting.py

ENTRYPOINT ["./aa_greeting.py"]
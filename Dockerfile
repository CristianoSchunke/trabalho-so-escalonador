FROM python:3.12-slim

# saída sem buffer e com acentuação correta no terminal
ENV PYTHONUNBUFFERED=1 \
    PYTHONIOENCODING=utf-8

WORKDIR /app

COPY src/ ./src/
COPY input/ ./input/
RUN mkdir -p output

# Argumentos extras do "docker run" são repassados ao simulador.
# Ex.: docker run --rm so-escalonador --quantum 4 --seed 7
ENTRYPOINT ["python", "src/escalonador.py"]
CMD []

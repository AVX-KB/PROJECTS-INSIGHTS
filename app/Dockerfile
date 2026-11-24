FROM python:3.11-slim

WORKDIR /app

# Eerst alleen de requirements: dan hoeft pip niet opnieuw bij elke codewijziging.
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY . .

EXPOSE 8080

# app.py start waitress (een echte server), niet de ontwikkelserver van Flask.
CMD ["python", "app.py"]

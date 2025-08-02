FROM python:3.11-slim

WORKDIR /app

# Copy requirements and install dependencies
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Copy the rest of the application code
COPY . .

# Set environment variables
ENV PYTHONUNBUFFERED=1
ENV PYTHONIOENCODING=UTF-8

# Expose the port the app runs on
EXPOSE 8001

# Run the application with reload for better error visibility
CMD ["uvicorn", "server:app", "--host", "0.0.0.0", "--port", "8001", "--reload", "--log-level", "debug"]

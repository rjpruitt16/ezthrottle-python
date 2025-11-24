# EZThrottle Python SDK Test App
# Uses local SDK (not published to PyPI yet)

FROM python:3.11-slim

WORKDIR /app

# Copy SDK source code
COPY ezthrottle /app/ezthrottle
COPY pyproject.toml /app/pyproject.toml
COPY README.md /app/README.md

# Install SDK dependencies
RUN pip install --no-cache-dir requests flask python-dotenv

# Install test app dependencies
RUN pip install --no-cache-dir fastapi uvicorn[standard] pydantic

# Copy test app
COPY test-app/app.py /app/app.py

# Expose port
EXPOSE 8080

# Run app
CMD ["python", "-m", "uvicorn", "app:app", "--host", "0.0.0.0", "--port", "8080"]

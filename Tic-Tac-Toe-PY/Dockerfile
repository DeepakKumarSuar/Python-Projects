# Use a lightweight Python base image
FROM python:3.10-slim

# Set working directory
WORKDIR /app

# Copy all files to container
COPY . .

# Install Python dependencies
RUN pip install --no-cache-dir -r requirements.txt

# Expose port (matches server.py default)
EXPOSE 8080

# Start the WebSocket + static file server
CMD ["python", "server.py"]

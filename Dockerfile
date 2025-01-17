# Use the official Python image from Docker Hub
FROM python:3.10-slim

# Set the working directory in the container
WORKDIR /app

# Copy the current directory contents into the container
COPY . /app

# Update pip and install dependencies
RUN pip install --no-cache-dir --upgrade pip \
    && pip install --no-cache-dir -r requirements.txt

# Expose the port your Flask app will run on
EXPOSE 5000

# Command to run your application
CMD ["gunicorn", "-b", "0.0.0.0:5000", "app:app"]

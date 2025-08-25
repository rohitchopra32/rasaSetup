#!/bin/sh

# Wait for database to be ready (if using external database)
echo "Starting Django application..."

# Wait for Rasa to be ready
echo "Waiting for Rasa server..."
python wait_for_rasa.py
if [ $? -ne 0 ]; then
    echo "Failed to wait for Rasa server"
    exit 1
fi

# Run migrations
python manage.py migrate --noinput

# Collect static files (if needed)
python manage.py collectstatic --noinput

# Start the server
python manage.py runserver 0.0.0.0:8000

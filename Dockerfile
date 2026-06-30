# ========================================================
# cantarella
# Don't Remove Credit 🥺
# Telegram Channel @cantarellabots
#
# Maintained & Updated by:
# Dhanpal Sharma
# GitHub: https://github.com/LastPerson07
# ========================================================

FROM python:3.10.13-slim-bullseye

# Prevent Python from creating .pyc files
ENV PYTHONDONTWRITEBYTECODE=1
# Ensure logs are shown instantly
ENV PYTHONUNBUFFERED=1

# Set working directory
WORKDIR /app

# Install system dependencies including ffmpeg and ffprobe
RUN apt-get update && apt-get install -y --no-install-recommends \
    ca-certificates \
    ffmpeg \
    && rm -rf /var/lib/apt/lists/*

# Verify ffmpeg and ffprobe installation
RUN ffmpeg -version && ffprobe -version

# Install Python dependencies
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Copy project files
COPY . .

# Create necessary directories
RUN mkdir -p downloads temp_thumbs

# Start ONLY the bot
# Flask keep_alive server handles port binding
CMD ["python3", "bot.py"]

# ========================================================
# cantarella
# Don't Remove Credit
# Telegram Channel @cantarellabots
#
# Updated & Managed by:
# Dhanpal Sharma | https://github.com/LastPerson07
# ========================================================

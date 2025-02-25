FROM python:3.9-slim

WORKDIR /workspaces/app

# Install system dependencies
RUN apt-get update && apt-get install -y \
    git \
    && apt-get clean \
    && rm -rf /var/lib/apt/lists/*

# We'll install Python requirements in postCreateCommand for faster rebuilds
COPY requirements.txt .
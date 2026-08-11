FROM python:3.12-slim

# Node (for ESLint), a JDK (javac for SpotBugs + java for Checkstyle/SpotBugs)
RUN apt-get update \
    && apt-get install -y --no-install-recommends nodejs npm default-jdk-headless \
    && rm -rf /var/lib/apt/lists/* \
    && npm install -g eslint --no-audit --no-fund

WORKDIR /app
COPY requirements.txt .
RUN pip install -r requirements.txt

# Download Checkstyle and SpotBugs (used by their linters)
COPY scripts/ scripts/
RUN python scripts/install_checkstyle.py && python scripts/install_spotbugs.py

COPY . .
CMD ["gunicorn", "-b", "0.0.0.0:5000", "run:app"]

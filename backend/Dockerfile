FROM python:3.13-slim

# Stockfish comes from the distro so nobody has to install an engine by hand.
# Debian drops it in /usr/games, which isn't on PATH — link it wherever it lands
# so the build fails loudly here rather than the engine stage failing at runtime.
RUN apt-get update \
    && apt-get install -y --no-install-recommends stockfish \
    && rm -rf /var/lib/apt/lists/* \
    && ln -s "$(dpkg -L stockfish | grep -m1 -E '^/usr/(games|s?bin|local/bin)/stockfish$')" /usr/local/bin/stockfish

WORKDIR /app

COPY requirements.txt requirements-dev.txt ./
RUN pip install --no-cache-dir -r requirements-dev.txt

COPY . .

ENV STOCKFISH_PATH=stockfish
EXPOSE 8000
CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]

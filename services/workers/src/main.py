import logging
import os
import socket
import time

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("BarVisionWorker")

# Container hostname is unique per replica, which keeps `--scale worker=N` working.
worker_id = os.getenv("WORKER_ID") or socket.gethostname()


def main():
    logger.info(f"[{worker_id}] BarVision Worker initialized successfully.")
    while True:
        time.sleep(10)


if __name__ == "__main__":
    main()
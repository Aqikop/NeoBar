import os
import time
import logging

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("BarVisionWorker")

worker_id = os.getenv("WORKER_ID", "worker-unknown")

def main():
    logger.info(f"[{worker_id}] BarVision Worker initialized successfully.")
    while True:
        time.sleep(10)

if __name__ == "__main__":
    main()

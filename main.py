import logging
import os
from pgbackup import Pgbackup

if __name__ == "__main__":
    logging.basicConfig(level=int(os.getenv("LOG_LEVEL", 20)), format="%(asctime)s - %(levelname)s - %(message)s")

    pgbackup = Pgbackup()
    pgbackup.start()

import logging
import logging.config

import config

logging.config.dictConfig(config.LOGGING_CONFIG)
LOGGER = logging.getLogger(config.LOGGER_NAME)


def main() -> None:
    print(config.ASCII_ART)
    LOGGER.info("ChunkDMesh orchestrator is ready.")


if __name__ == "__main__":
    main()

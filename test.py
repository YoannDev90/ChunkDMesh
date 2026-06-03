import logging

import server.logging_utils

if __name__ == "__main__":
    logger = server.logging_utils.setup_logging()
    server.logging_utils.log_a(logging.INFO, "hello_world")
    server.logging_utils.log_a(logging.WARNING, "sample_log_with_param", param="test")
    server.logging_utils.log_a(logging.ERROR, "sample_log_with_param", param="test")
    server.logging_utils.log_a(logging.CRITICAL, "sample_log_with_param", param="test")

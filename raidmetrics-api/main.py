import os
import uvicorn
import logging
import copy
import sys
from uvicorn.logging import AccessFormatter

class TableAccessFormatter(AccessFormatter):
    def formatMessage(self, record):
        # Only format access logs
        if hasattr(record, 'client_addr') and hasattr(record, 'request_line') and hasattr(record, 'status_code'):
            status = record.status_code
            color = '\033[92m' if 200 <= status < 300 else ('\033[93m' if 300 <= status < 400 else '\033[91m')
            reset = '\033[0m'
            return f"[API] {record.asctime} | {color}{status}{reset} | {record.client_addr:>15} | {record.request_line}"
        return super().formatMessage(record)

if __name__ == "__main__":
    # Configure custom logging format similar to Gin
    log_config = copy.deepcopy(uvicorn.config.LOGGING_CONFIG)
    log_config["formatters"]["access"]["()"] = TableAccessFormatter
    log_config["formatters"]["access"]["fmt"] = "[API] %(asctime)s | %(status_code)s | %(client_addr)s | %(request_line)s"
    log_config["formatters"]["default"]["fmt"] = '[API] %(asctime)s | %(levelname)s | %(message)s'
    
    uvicorn.run(
        app="api.init:app",
        host=os.getenv("RAIDMETRICS_PORTAL_API_HOST", "0.0.0.0"),
        port=int(os.getenv("RAIDMETRICS_PORTAL_API_PORT", 8000)),
        reload=os.getenv("RAIDMETRICS_PORTAL_API_RELOAD", "true").lower() == "true",
        log_level="info",
        access_log=True,
        use_colors=True,
        log_config=log_config,
    )
# SPDX-License-Identifier: AGPL-3.0-or-later
"""Structured (JSON lines) log formatter: ``LOG_FORMAT=json``."""
import json
import logging
import time


class JsonFormatter(logging.Formatter):
    RESERVED = set(vars(logging.makeLogRecord({})))

    def format(self, record: logging.LogRecord) -> str:
        data = {
            "ts": time.strftime("%Y-%m-%dT%H:%M:%S", time.gmtime(record.created)) + f".{int(record.msecs):03d}Z",
            "level": record.levelname,
            "logger": record.name,
            "msg": record.getMessage(),
        }
        for key, value in vars(record).items():
            if key not in self.RESERVED and not key.startswith("_"):
                data[key] = value
        if record.exc_info:
            data["exc"] = self.formatException(record.exc_info)
        return json.dumps(data, default=str)

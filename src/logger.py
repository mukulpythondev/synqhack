import logging
import json
from datetime import datetime

class StructuredJSONFormatter(logging.Formatter):
    def format(self, record):
        log_record = {
            "timestamp": datetime.fromtimestamp(record.created).isoformat(),
            "level": record.levelname,
            "logger": record.name,
            "message": record.getMessage()
        }
        
        # Add any extra structured fields passed in `extra={...}`
        if hasattr(record, 'structured_data'):
            for k, v in record.structured_data.items():
                if k not in log_record:
                    log_record[k] = v
                    
        return json.dumps(log_record)

def get_structured_logger(name="MeridianFreight"):
    logger = logging.getLogger(name)
    if not logger.handlers:
        logger.setLevel(logging.INFO)
        handler = logging.StreamHandler()
        handler.setFormatter(StructuredJSONFormatter())
        logger.addHandler(handler)
    return logger

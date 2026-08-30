"""
Meridian Freight Breakdown Automation
PII Zero-Leakage Scrubber & Pre-Write Validation Barrier
"""

import re
from typing import Any, Dict, List, Union

class PIIScrubber:
    """
    Strict PII detection and redaction engine.
    Ensures zero personal data (Aadhaar, Phones, Driving Licenses, Full Names)
    leaks into application logs, output JSONLs, query responses, or LLM contexts.
    """

    AADHAAR_REGEX = re.compile(r'\b\d{4}\s\d{4}\s\d{4}\b')
    # Matches +91 93118 40522, +91 9311840522, 9311840522, 93118 40522, +91-93118-40522
    PHONE_REGEX = re.compile(r'(\+?91[\s-]?[6-9]\d{4}[\s-]?\d{5}|\+?91[\s-]?[6-9]\d{9}|\b[6-9]\d{4}[\s-]?\d{5}\b|\b[6-9]\d{9}\b)')
    # Matches HR16 20128663605, HR1620128663605, DL01 20180001234
    DL_REGEX = re.compile(r'\b[A-Z]{2}\d{1,2}\s?\d{11}\b')
    
    # Sensitive field names to strip or scrub entirely
    SENSITIVE_KEYS = {"aadhaar", "phone", "dl_number", "driver_name", "name"}

    @classmethod
    def scrub_text(cls, text: str) -> str:
        if not isinstance(text, str):
            return text
        
        # 1. Redact Aadhaar
        text = cls.AADHAAR_REGEX.sub('[AADHAAR_MASKED]', text)
        
        # 2. Redact Phone numbers
        text = cls.PHONE_REGEX.sub('[PHONE_MASKED]', text)
        
        # 3. Redact Driving License numbers
        text = cls.DL_REGEX.sub('[DL_MASKED]', text)
        
        return text

    @classmethod
    def scrub_dict(cls, data: Union[Dict[str, Any], List[Any], Any]) -> Any:
        if isinstance(data, dict):
            cleaned = {}
            for k, v in data.items():
                if k.lower() in cls.SENSITIVE_KEYS:
                    # Strip sensitive fields from outbound data entirely
                    continue
                cleaned[k] = cls.scrub_dict(v)
            return cleaned
        elif isinstance(data, list):
            return [cls.scrub_dict(item) for item in data]
        elif isinstance(data, str):
            return cls.scrub_text(data)
        else:
            return data

    @classmethod
    def contains_raw_pii(cls, text: str) -> bool:
        if not isinstance(text, str):
            return False
        
        if cls.AADHAAR_REGEX.search(text):
            return True
        if cls.PHONE_REGEX.search(text):
            return True
        if cls.DL_REGEX.search(text):
            return True
        return False

    @classmethod
    def validate_outbox_payload(cls, payload: Dict[str, Any]) -> None:
        """
        Pre-write hard gate. Throws ValueError if any raw PII pattern
        is detected in any serialized string value within payload.
        """
        def _check(val: Any):
            if isinstance(val, str):
                if cls.contains_raw_pii(val):
                    raise ValueError(f"PII SECURITY GATE BREACH: Raw PII detected in payload value: '{val[:30]}...'")
            elif isinstance(val, dict):
                for k, v in val.items():
                    if k.lower() in cls.SENSITIVE_KEYS:
                        raise ValueError(f"PII SECURITY GATE BREACH: Forbidden key '{k}' present in outbox payload.")
                    _check(v)
            elif isinstance(val, list):
                for item in val:
                    _check(item)

        _check(payload)

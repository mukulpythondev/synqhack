import re
with open('src/llm_adapter.py', 'r', encoding='utf-8') as f:
    code = f.read()

idx_start = code.find('class GeminiPerception(PerceptionProvider):')
idx_end = code.find('class PerceptionRouter:')

new_class = '''class GeminiPerception(PerceptionProvider):
    """
    Gemini 2.5 Flash perception adapter using official google-genai SDK.
    Activated ONLY when deterministic perception is ambiguous or low-confidence.
    """

    def __init__(self, api_key: Optional[str] = None, model: Optional[str] = None, db_path: Optional[str] = None):
        from src.config import STATE_DB_PATH
        import os
        self.db_path = str(db_path) if db_path else str(STATE_DB_PATH)
        
        # Kill switch
        if str(os.getenv("GEMINI_ENABLED", "true")).lower() != "true":
            self.api_key = None
            self.client = None
            return
            
        if api_key is not None:
            self.api_key = api_key if api_key != "" else None
        else:
            self.api_key = os.getenv("GEMINI_API_KEY")

        self.model_name = model or os.getenv("GEMINI_MODEL", "gemini-2.5-flash")
        self.client = None

        if self.api_key:
            try:
                from google import genai
                self.client = genai.Client(api_key=self.api_key)
            except Exception as e:
                logger.warning(f"Failed to initialize google-genai client: {e}")
                self.client = None
                
        import sqlite3
        with sqlite3.connect(self.db_path) as conn:
            conn.execute("""
                CREATE TABLE IF NOT EXISTS gemini_cache (
                    content_hash TEXT,
                    model TEXT,
                    schema_version TEXT,
                    extraction_version TEXT,
                    validated_facts_json TEXT,
                    created_at TEXT,
                    PRIMARY KEY (content_hash, model, schema_version)
                )
            """)
            conn.commit()

    @property
    def is_available(self) -> bool:
        import os
        if str(os.getenv("GEMINI_ENABLED", "true")).lower() != "true":
            return False
        return self.client is not None

    def extract_unstructured_facts(self, text: str) -> PerceptionFacts:
        if not self.is_available:
            return PerceptionFacts(confidence=0.0, extraction_notes="Gemini unavailable (no API key or client error)")

        sanitized_text = PIIScrubber.scrub_text(text)
        
        import hashlib, sqlite3, json
        from datetime import datetime
        content_hash = hashlib.sha256(sanitized_text.encode('utf-8')).hexdigest()
        schema_v = "v1"
        
        try:
            with sqlite3.connect(self.db_path) as conn:
                cursor = conn.cursor()
                cursor.execute("SELECT validated_facts_json FROM gemini_cache WHERE content_hash=? AND model=? AND schema_version=?", (content_hash, self.model_name, schema_v))
                row = cursor.fetchone()
                if row:
                    data = json.loads(row[0])
                    return PerceptionFacts(
                        confidence=data.get("confidence", 0.8),
                        temporal_reference=data.get("temporal_reference"),
                        extracted_entities=data.get("extracted_entities"),
                        inferred_issue=data.get("inferred_issue"),
                        operational_notes=data.get("operational_notes", []),
                        extraction_notes="Loaded from cache"
                    )
        except Exception as e:
            logger.warning(f"Cache read error: {e}")

        sanitized_prompt_text = sanitized_text

        system_instruction = (
            "You are an operational fact extractor for Meridian Freight. "
            "Extract verifiable facts from the provided snippet. "
            "Do NOT hallucinate client names or vehicle registrations. "
            "Return JSON ONLY: {"
            "  \\"confidence\\": float (0.0 to 1.0), "
            "  \\"temporal_reference\\": string or null, "
            "  \\"extracted_entities\\": {\\"client\\": string, \\"vehicle\\": string, \\"driver\\": string}, "
            "  \\"inferred_issue\\": string, "
            "  \\"operational_notes\\": [string]"
            "}"
        )
        
        try:
            from google import genai
            from google.genai import types
            
            response = self.client.models.generate_content(
                model=self.model_name,
                contents=sanitized_prompt_text,
                config=types.GenerateContentConfig(
                    system_instruction=system_instruction,
                    temperature=0.0,
                    response_mime_type="application/json",
                )
            )
            
            raw_json = response.text
            raw_json = raw_json.replace('```json', '').replace('```', '').strip()
            data = json.loads(raw_json)
            
            facts = PerceptionFacts(
                confidence=float(data.get("confidence", 0.8)),
                temporal_reference=data.get("temporal_reference"),
                extracted_entities=data.get("extracted_entities"),
                inferred_issue=data.get("inferred_issue"),
                operational_notes=data.get("operational_notes", []),
                extraction_notes="Gemini extraction successful"
            )
            
            try:
                with sqlite3.connect(self.db_path) as conn:
                    cache_data = {
                        "confidence": facts.confidence,
                        "temporal_reference": facts.temporal_reference,
                        "extracted_entities": facts.extracted_entities,
                        "inferred_issue": facts.inferred_issue,
                        "operational_notes": facts.operational_notes
                    }
                    conn.execute("""
                        INSERT OR REPLACE INTO gemini_cache (
                            content_hash, model, schema_version, extraction_version, validated_facts_json, created_at
                        ) VALUES (?, ?, ?, ?, ?, ?)
                    """, (content_hash, self.model_name, schema_v, "1", json.dumps(cache_data), datetime.now().isoformat()))
                    conn.commit()
            except Exception as e:
                logger.warning(f"Cache write error: {e}")
                
            return facts
        except Exception as e:
            logger.warning(f"Gemini API failure: {e}")
            return PerceptionFacts(confidence=0.0, extraction_notes=f"Gemini extraction failed: {e}")

    def propose_schema_mapping(self, unrecognized_key: str, sample_value: Any) -> Optional[str]:
        return None

'''

if idx_start != -1 and idx_end != -1:
    with open('src/llm_adapter.py', 'w', encoding='utf-8') as f:
        f.write(code[:idx_start] + new_class + code[idx_end:])
    print('Successfully patched src/llm_adapter.py')
else:
    print('Could not find indices')

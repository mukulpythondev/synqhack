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
        """
        Extracts structured facts from unstructured text using Gemini.
        Pre-scrubs all personal data before dispatch.
        """
        if not self.is_available:
            return PerceptionFacts(confidence=0.0, extraction_notes="Gemini unavailable (no API key or client error)")

        # PII Boundary: Strict Pre-Ingestion Scrubbing
        sanitized_prompt_text = PIIScrubber.scrub_text(text)

        import hashlib, sqlite3, json
        from datetime import datetime
        content_hash = hashlib.sha256(sanitized_prompt_text.encode('utf-8')).hexdigest()
        schema_v = "v1"
        
        try:
            with sqlite3.connect(self.db_path) as conn:
                cursor = conn.cursor()
                cursor.execute("SELECT validated_facts_json FROM gemini_cache WHERE content_hash=? AND model=? AND schema_version=?", (content_hash, self.model_name, schema_v))
                row = cursor.fetchone()
                if row:
                    data = json.loads(row[0])
                    return PerceptionFacts.model_validate(data)
        except Exception as e:
            logger.warning(f"Cache read error: {e}")

        system_instruction = (
            "You are a strict factual perception extractor for a freight transportation system. "
            "Extract ONLY information explicitly present in the provided text. "
            "Never invent missing values. Use null for unknown fields. "
            "Never infer an operational decision, never recommend a vehicle, never invent an SLA or business rule. "
            "Never output personal data (phones, Aadhaar, driving licenses, full names). "
            "Return structured JSON matching the PerceptionFacts schema."
        )

        try:
            from google.genai import types
            response = self.client.models.generate_content(
                model=self.model_name,
                contents=[
                    types.Content(
                        role="user",
                        parts=[
                            types.Part.from_text(text=f"{system_instruction}\\n\\nTEXT TO EXTRACT:\\n\\"\\"\\"{sanitized_prompt_text}\\"\\"\\"")
                        ]
                    )
                ],
                config=types.GenerateContentConfig(
                    response_mime_type="application/json",
                    response_schema=PerceptionFacts,
                    temperature=0.0, # Zero temperature for maximum deterministic stability
                )
            )

            if response and response.text:
                data = json.loads(response.text)
                facts = PerceptionFacts.model_validate(data)
                
                # Write to Cache
                try:
                    with sqlite3.connect(self.db_path) as conn:
                        cache_data = data
                        cache_data["extraction_notes"] = "Loaded from cache"
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
            logger.warning(f"Gemini unstructured extraction failed safely: {e}")

        return PerceptionFacts(confidence=0.0, extraction_notes="Gemini extraction error or invalid response")

    def propose_schema_mapping(self, unrecognized_key: str, sample_value: Any) -> Optional[str]:
        """
        Proposes a canonical key for an unrecognized column name.
        Result is strictly validated against ALLOWED_CANONICAL_KEYS.
        """
        if not self.is_available:
            return None

        prompt = (
            f"Given an unrecognized freight data column name '{unrecognized_key}' with sample value '{sample_value}', "
            f"map it to the best matching canonical field from this strict whitelist: {sorted(list(ALLOWED_CANONICAL_KEYS))}. "
            "If no reasonable match exists, return proposed_canonical_key as null. "
            "Return structured JSON matching SchemaMappingProposal."
        )

        import hashlib, sqlite3, json
        from datetime import datetime
        cache_key = hashlib.sha256(f"{unrecognized_key}_{sample_value}".encode('utf-8')).hexdigest()
        
        try:
            with sqlite3.connect(self.db_path) as conn:
                cursor = conn.cursor()
                cursor.execute("SELECT validated_facts_json FROM gemini_cache WHERE content_hash=? AND model=? AND schema_version=?", (cache_key, self.model_name, "schema_v1"))
                row = cursor.fetchone()
                if row:
                    return json.loads(row[0]).get("proposed_key")
        except Exception:
            pass

        try:
            from google.genai import types
            response = self.client.models.generate_content(
                model=self.model_name,
                contents=prompt,
                config=types.GenerateContentConfig(
                    response_mime_type="application/json",
                    response_schema=SchemaMappingProposal,
                    temperature=0.0,
                )
            )
            if response and response.text:
                data = json.loads(response.text)
                proposal = SchemaMappingProposal.model_validate(data)
                if proposal.proposed_canonical_key in ALLOWED_CANONICAL_KEYS and proposal.confidence >= 0.7:
                    try:
                        with sqlite3.connect(self.db_path) as conn:
                            conn.execute("""
                                INSERT OR REPLACE INTO gemini_cache (
                                    content_hash, model, schema_version, extraction_version, validated_facts_json, created_at
                                ) VALUES (?, ?, ?, ?, ?, ?)
                            """, (cache_key, self.model_name, "schema_v1", "1", json.dumps({"proposed_key": proposal.proposed_canonical_key}), datetime.now().isoformat()))
                            conn.commit()
                    except Exception:
                        pass
                    return proposal.proposed_canonical_key
        except Exception as e:
            logger.warning(f"Gemini schema mapping proposal failed safely: {e}")

        return None

    def interpret_query_intent(self, query_text: str) -> Optional[QueryIntent]:
        """
        Interprets natural language question intent into safe structured query parameters.
        Does NOT answer the question itself; answers are retrieved locally from verified ContextStore.
        """
        if not self.is_available:
            return None

        sanitized_query = PIIScrubber.scrub_text(query_text)
        
        import hashlib, sqlite3, json
        from datetime import datetime
        cache_key = hashlib.sha256(f"intent_{sanitized_query}".encode('utf-8')).hexdigest()
        
        try:
            with sqlite3.connect(self.db_path) as conn:
                cursor = conn.cursor()
                cursor.execute("SELECT validated_facts_json FROM gemini_cache WHERE content_hash=? AND model=? AND schema_version=?", (cache_key, self.model_name, "intent_v1"))
                row = cursor.fetchone()
                if row:
                    return QueryIntent.model_validate(json.loads(row[0]))
        except Exception:
            pass

        prompt = (
            f"Analyze this operational query: '{sanitized_query}'. "
            "Extract target entity type (vehicle, client, corridor, rule), entity identifier, and intent topic. "
            "Never generate an answer. Extract intent parameters only. "
            "Return structured JSON matching QueryIntent."
        )

        try:
            from google.genai import types
            response = self.client.models.generate_content(
                model=self.model_name,
                contents=prompt,
                config=types.GenerateContentConfig(
                    response_mime_type="application/json",
                    response_schema=QueryIntent,
                    temperature=0.0,
                )
            )
            if response and response.text:
                data = json.loads(response.text)
                
                try:
                    with sqlite3.connect(self.db_path) as conn:
                        conn.execute("""
                            INSERT OR REPLACE INTO gemini_cache (
                                content_hash, model, schema_version, extraction_version, validated_facts_json, created_at
                            ) VALUES (?, ?, ?, ?, ?, ?)
                        """, (cache_key, self.model_name, "intent_v1", "1", json.dumps(data), datetime.now().isoformat()))
                        conn.commit()
                except Exception:
                    pass
                
                return QueryIntent.model_validate(data)
        except Exception as e:
            logger.warning(f"Gemini query intent interpretation failed safely: {e}")

        return None

'''

if idx_start != -1 and idx_end != -1:
    with open('src/llm_adapter.py', 'w', encoding='utf-8') as f:
        f.write(code[:idx_start] + new_class + code[idx_end:])
    print('Successfully patched src/llm_adapter.py')
else:
    print('Could not find indices')

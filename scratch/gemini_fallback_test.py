from src.pipeline import BreakdownPipeline
import os
import json

# Force Gemini to be enabled
os.environ["GEMINI_ENABLED"] = "true"
if not os.environ.get("GEMINI_API_KEY"):
    os.environ["GEMINI_API_KEY"] = "fake-key-for-test" # If we have a real one, it will use it from .env

def run():
    print("Initializing pipeline...")
    pipeline = BreakdownPipeline()
    
    # We create a ticket that is very unstructured/ambiguous
    ambiguous_ticket = {
        "ticket_id": "TKT-GEMINI-TEST-01",
        "client_name": "Apex Chemicals",
        "fault": "Kal raat wali gaadi from Delhi to Kanpur got stuck near Agra, driver is Mohan.",
        "created_at": "2026-08-30T10:00:00Z"
    }
    
    print("\nProcessing ambiguous ticket...")
    with open("scratch/temp_ticket.json", "w") as f:
        json.dump([ambiguous_ticket], f)
    pipeline.process_ticket_queue("scratch/temp_ticket.json")
    
    # Now let's inspect the audit log
    print("\nChecking audit log for Gemini activity...")
    with open("audit/audit.jsonl", "r") as f:
        for line in f:
            if "TKT-GEMINI-TEST-01" in line:
                data = json.loads(line)
                if "extraction_method" in data.get("input_data_summary", {}):
                    print(f"Extraction Method: {data['input_data_summary']['extraction_method']}")
                print(f"Step: {data.get('step_name')} -> {data.get('decision')}")

if __name__ == "__main__":
    run()

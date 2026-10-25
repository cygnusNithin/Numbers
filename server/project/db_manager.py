# db_manager.py
from pymongo import MongoClient
from datetime import datetime
import logging
from typing import Dict, List

logger = logging.getLogger(__name__)

class DBManager:
    """Manage MongoDB connection and data storage."""
    
    def __init__(self, uri: str, db_name: str, collection_name: str):
        self.client = MongoClient(uri)
        self.db = self.client[db_name]
        self.collection = self.db[collection_name]
        
        # Create indexes
        self.collection.create_index("extraction_id", unique=True)
        self.collection.create_index("prize")
        self.collection.create_index("date")
        
        logger.info(f"Connected to MongoDB: {db_name}/{collection_name}")
    
    def create_extraction_record(self, prize: int, extraction_date: str, entries: List[Dict]) -> Dict:
        """
        Create a new extraction record.
        
        Document structure:
        {
            "extraction_id": "4th_20250115_001",
            "prize": 4,
            "extraction_date": "2025-01-15",
            "total_numbers": 19,
            "expected_numbers": 19,
            "status": "in_progress",  # or "completed", "validation_failed"
            "entries": [
                {
                    "entry_id": 1,
                    "spin": 1,
                    "roller": 1,
                    "number": "0214",
                    "confidence": 0.95,
                    "digit_confidences": [0.98, 0.95, 0.92, 0.95],
                    "timestamp": "00:45",
                    "frame_idx": 1234,
                    "status": "confirmed",  # or "pending", "corrected"
                    "notes": ""
                },
                ...
            ],
            "created_at": ISODate("2025-01-15T10:30:00Z"),
            "updated_at": ISODate("2025-01-15T10:30:00Z")
        }
        """
        extraction_id = f"{prize}th_{extraction_date.replace('-', '')}_{self.collection.count_documents({'prize': prize}) + 1:03d}"
        
        record = {
            "extraction_id": extraction_id,
            "prize": prize,
            "extraction_date": extraction_date,
            "total_numbers": len(entries),
            "expected_numbers": 19,  # Hardcoded for now
            "status": "in_progress",
            "entries": entries,
            "created_at": datetime.utcnow(),
            "updated_at": datetime.utcnow()
        }
        
        result = self.collection.insert_one(record)
        logger.info(f"Created extraction record: {extraction_id}")
        return record
    
    def update_entry(self, extraction_id: str, entry_id: int, updates: Dict) -> bool:
        """Update a single entry in an extraction record."""
        result = self.collection.update_one(
            {"extraction_id": extraction_id, "entries.entry_id": entry_id},
            {
                "$set": {
                    "entries.$.number": updates.get("number"),
                    "entries.$.confidence": updates.get("confidence"),
                    "entries.$.status": updates.get("status", "confirmed"),
                    "entries.$.notes": updates.get("notes", ""),
                    "updated_at": datetime.utcnow()
                }
            }
        )
        return result.modified_count > 0
    
    def get_extraction_record(self, extraction_id: str) -> Dict:
        """Retrieve extraction record by ID."""
        return self.collection.find_one({"extraction_id": extraction_id})
    
    def mark_extraction_complete(self, extraction_id: str) -> bool:
        """Mark extraction as completed."""
        result = self.collection.update_one(
            {"extraction_id": extraction_id},
            {
                "$set": {
                    "status": "completed",
                    "updated_at": datetime.utcnow()
                }
            }
        )
        return result.modified_count > 0
    
    def close(self):
        """Close MongoDB connection."""
        self.client.close()
        logger.info("Closed MongoDB connection")
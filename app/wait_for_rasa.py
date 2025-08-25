#!/usr/bin/env python3
"""
Wait for Rasa server to be ready before starting Django
"""
import os
import time
import requests
import sys

def wait_for_rasa():
    """Wait for Rasa server to be ready"""
    rasa_url = os.getenv("RASA_URL", "http://rasa:5005")
    max_attempts = 60  # 5 minutes max wait
    attempt = 0
    
    print(f"Waiting for Rasa server at {rasa_url}...")
    
    while attempt < max_attempts:
        try:
            # Try to connect to Rasa status endpoint
            response = requests.get(f"{rasa_url}/status", timeout=5)
            if response.status_code == 200:
                print("✅ Rasa server is ready!")
                return True
        except requests.exceptions.RequestException:
            pass
        
        attempt += 1
        print(f"⏳ Attempt {attempt}/{max_attempts}: Rasa not ready yet, waiting 5 seconds...")
        time.sleep(5)
    
    print("❌ Rasa server failed to start within timeout period")
    return False

if __name__ == "__main__":
    if not wait_for_rasa():
        sys.exit(1)

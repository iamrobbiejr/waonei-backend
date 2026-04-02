import os
import requests
import time
import argparse
import sys
from dotenv import load_dotenv

# Load environment variables
load_dotenv()

API_URL = os.getenv("API_URL", "http://localhost:8000")

def submit_violation(image_path, violation_type=None, vehicle_plate="TEST-999"):
    """Submit a violation report to the backend API"""
    if not os.path.exists(image_path):
        print(f"Error: File not found at {image_path}")
        return None

    print(f"\n[+] Submitting report for {image_path}...")
    
    # Prepare the multipart form-data
    with open(image_path, 'rb') as f:
        files = {
            'file': (os.path.basename(image_path), f, 'image/jpeg')
        }
        data = {
            'violation_type': violation_type or 'not_specified',
            'vehicle_plate': vehicle_plate,
            'latitude': -1.286389,  # Default mock location (Nairobi)
            'longitude': 36.817223,
            'location_description': 'Office Test Lab'
        }
        
        try:
            response = requests.post(f"{API_URL}/report", files=files, data=data)
            response.raise_for_status()
            
            result = response.json()
            report_id = result.get('report_id')
            print(f"[*] Report submitted! ID: {report_id}")
            print(f"[*] Task queued (ID: {result.get('task_id')})")
            return report_id
        except Exception as e:
            print(f"[-] Submission failed: {str(e)}")
            if hasattr(e, 'response') and e.response is not None:
                 print(f"    Response: {e.response.text}")
            return None

def poll_report_status(report_id, timeout=60, interval=2):
    """Poll the report status until AI analysis is complete or timeout"""
    print(f"\n[+] Waiting for AI analysis results (Timeout: {timeout}s)...")
    
    start_time = time.time()
    while time.time() - start_time < timeout:
        try:
            response = requests.get(f"{API_URL}/report/{report_id}")
            response.raise_for_status()
            
            data = response.json()
            report = data.get('report', {})
            status = report.get('status')
            
            if status == 'verified':
                print(f"\n[SUCCESS] AI verification complete!")
                print(f"Violation Type: {report.get('violation_type')}")
                print(f"Confidence Score: {report.get('confidence_score')}")
                print(f"AI Details: {report.get('details', {}).get('description')}")
                return report
            elif status in ['failed', 'rejected']:
                print(f"\n[FAILED] Analysis failed or report rejected.")
                print(f"Status: {status}")
                return report
            elif status == 'no_violation':
                print(f"\n[INFO] No traffic violation detected in this image.")
                return report
                
            # Still pending?
            print(f"Status: {status}... (waiting {interval}s)")
            time.sleep(interval)
            
        except Exception as e:
            print(f"[-] Error checking status: {str(e)}")
            time.sleep(interval)
            
    print("\n[-] Polling timed out. The worker might be taking longer or is offline.")
    return None

def main():
    parser = argparse.ArgumentParser(description="Test Traffic Violation API locally")
    parser.add_argument("--image", required=True, help="Path to the sample image file")
    parser.add_argument("--type", help="Reported violation type (no_helmet, red_light, etc.)")
    parser.add_argument("--plate", default="TEST-123", help="Mock vehicle plate number")
    
    args = parser.parse_args()
    
    # 1. Submit the report
    report_id = submit_violation(args.image, args.type, args.plate)
    
    # 2. Poll for results
    if report_id:
        poll_report_status(report_id)

if __name__ == "__main__":
    main()

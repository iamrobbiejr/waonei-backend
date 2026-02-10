import os
import requests
import sys
from dotenv import load_dotenv
from supabase import create_client, Client

# Load environment variables
load_dotenv()

SUPABASE_URL = os.getenv("SUPABASE_URL")
SUPABASE_KEY = os.getenv("SUPABASE_SERVICE_ROLE_KEY")
API_URL = "http://localhost:8000"

if not SUPABASE_URL or not SUPABASE_KEY:
    print("Error: SUPABASE_URL and SUPABASE_SERVICE_ROLE_KEY must be set in .env")
    sys.exit(1)

# Initialize Supabase client
supabase: Client = create_client(SUPABASE_URL, SUPABASE_KEY)

# Test User Credentials
ADMIN_EMAIL = "admin@example.com"
ADMIN_PASSWORD = "securepassword123"
NEW_USER_EMAIL = "newuser@example.com"
NEW_USER_PASSWORD = "newuserpassword123"

def setup_admin_user():
    print(f"Setting up admin user: {ADMIN_EMAIL}")
    try:
        # Check if user exists (this is a bit hacky with admin api, usually we just try to sign in)
        # But we can try to create it, if it fails it might already exist
        
        # We can't easily check 'exists' without listing all users which might be slow/limited.
        # So we'll try to create it. If it fails with 'User already registered', we'll assume it exists.
        
        attributes = {
            "email": ADMIN_EMAIL,
            "password": ADMIN_PASSWORD,
            "email_confirm": True,
            "user_metadata": {"role": "admin"}
        }
        user = supabase.auth.admin.create_user(attributes)
        print("Admin user created/verified via Supabase Admin API.")
    except Exception as e:
        print(f"Note on admin setup: {e}") 
        # It's possible the user exists, let's proceed to try login


def test_login():
    print(f"\nTesting Login for {ADMIN_EMAIL}...")
    response = requests.post(f"{API_URL}/auth/login", json={
        "email": ADMIN_EMAIL,
        "password": ADMIN_PASSWORD
    })
    
    if response.status_code == 200:
        print("Login successful!")
        data = response.json()
        token = data.get("access_token")
        print(f"Received Token: {token[:20]}...")
        return token
    else:
        print(f"Login failed: {response.status_code} - {response.text}")
        return None

def test_create_user(token):
    print(f"\nTesting Create User (as Admin)...")
    headers = {"Authorization": f"Bearer {token}"}
    payload = {
        "email": NEW_USER_EMAIL,
        "password": NEW_USER_PASSWORD,
        "role": "user"
    }
    
    response = requests.post(f"{API_URL}/admin/users", json=payload, headers=headers)
    
    if response.status_code == 200:
        print("User creation successful!")
        print(response.json())
        return True
    else:
        print(f"User creation failed: {response.status_code} - {response.text}")
        return False

def main():
    setup_admin_user()
    
    # Wait a bit for propagation if created (usually unused for immediate login but good practice)
    import time
    time.sleep(1)
    
    token = test_login()
    if token:
        test_create_user(token)
    else:
        print("Skipping create user test due to login failure.")

if __name__ == "__main__":
    main()

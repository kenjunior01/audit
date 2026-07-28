import requests
import uuid
import os

BASE_URL = "http://localhost:8000/django/api"

def test_registration_flow():
    email = f"test_{uuid.uuid4().hex[:8]}@example.com"
    password = "Password123!"
    name = "Test User"
    company = "Test Corp"
    
    print(f"1. Registering user {email}...")
    resp = requests.post(f"{BASE_URL}/auth/register", json={
        "email": email,
        "password": password,
        "name": name,
        "company_name": company,
        "sector": "SaaS"
    })
    
    if resp.status_code != 200:
        print(f"Registration failed: {resp.text}")
        return
    
    data = resp.json()
    token = data['token']
    user_id = data['user_id']
    print(f"Registration successful. Token: {token[:10]}... User ID: {user_id}")
    
    # Verify Login
    print("2. Verifying login...")
    resp = requests.post(f"{BASE_URL}/auth/login", json={
        "email": email,
        "password": password
    })
    
    if resp.status_code != 200:
        print(f"Login failed: {resp.text}")
        return
        
    print("Login successful.")
    
    # Upload KYC Document
    print("3. Uploading KYC document...")
    
    # Create a dummy file
    with open("dummy_kyc.txt", "w") as f:
        f.write(f"This is a dummy KYC document {uuid.uuid4()}.")
        
    headers = {"Authorization": f"Bearer {token}"}
    with open("dummy_kyc.txt", "rb") as f_obj:
        files = {'file': f_obj}
        data = {
            'title': 'KYC Test',
            'doc_type': 'KYC_Credential',
            'country': 'Brazil'
        }
        
        resp = requests.post(f"{BASE_URL}/upload/document", headers=headers, files=files, data=data)
    
    if resp.status_code == 200:
        doc_id = resp.json().get('id')
        print(f"KYC Upload successful. Document ID: {doc_id}")
    else:
        print(f"KYC Upload failed: {resp.text}")
        
    try:
        os.remove("dummy_kyc.txt")
    except Exception as e:
        print(f"Warning: Could not remove dummy_kyc.txt: {e}")

    # Security Test: Upload Malicious File (Empty File triggers 'Empty File' hash)
    print("4. Testing Security: Uploading empty file (Mock Virus)...")
    with open("virus.pdf", "wb") as f:
        pass # Empty file
        
    with open("virus.pdf", "rb") as f_obj:
        files = {'file': f_obj}
        resp = requests.post(f"{BASE_URL}/upload/document", headers=headers, files=files, data=data)
    
    if resp.status_code == 400 and "Security Alert" in resp.text:
        print("Security Check Passed: Malicious file blocked.")
    else:
        print(f"Security Check Failed: {resp.status_code} - {resp.text}")
        
    try:
        os.remove("virus.pdf")
    except Exception as e:
        print(f"Warning: Could not remove virus.pdf: {e}")
    print("Test completed.")

if __name__ == "__main__":
    test_registration_flow()

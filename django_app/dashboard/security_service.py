import hashlib
import os

# Known bad hashes (mock database of malicious files)
BAD_HASHES = {
    'e3b0c44298fc1c149afbf4c8996fb92427ae41e4649b934ca495991b7852b855': 'Empty File',
    '5e884898da28047151d0e56f8dc6292773603d0d6aabbdd62a11ef721d1542d8': 'Test Virus Signature'
}

def calculate_file_hash(file_obj):
    """Calculates SHA-256 hash of a file object."""
    hasher = hashlib.sha256()
    for chunk in file_obj.chunks():
        hasher.update(chunk)
    return hasher.hexdigest()

def scan_file(file_obj, file_hash=None):
    """
    Simulates a virus scan.
    Returns:
        status (str): 'Clean', 'Infected', 'Skipped'
        message (str): Details about the scan result
    """
    if not file_hash:
        file_hash = calculate_file_hash(file_obj)
        
    if file_hash in BAD_HASHES:
        return 'Infected', f"Known malicious file: {BAD_HASHES[file_hash]}"
    
    # Simulate heuristic check (e.g., check for dangerous extensions masquerading)
    ext = os.path.splitext(file_obj.name)[1].lower()
    if ext in ['.exe', '.bat', '.cmd', '.sh', '.vbs']:
        return 'Infected', f"Blocked file type: {ext}"
        
    # In a real scenario, we would send the file to ClamAV or VirusTotal here
    # For now, we assume it's clean if it passes the basic checks
    return 'Clean', 'No threats detected'

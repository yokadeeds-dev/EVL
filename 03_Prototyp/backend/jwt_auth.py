import hmac
import hashlib
import json
import os
import time
import base64

SECRET_KEY = os.environ.get("JWT_SECRET_KEY", "")
if not SECRET_KEY:
    raise RuntimeError("JWT_SECRET_KEY ist nicht gesetzt! Bitte in .env eintragen.")

def _b64enc(data: bytes) -> str:
    return base64.urlsafe_b64encode(data).decode('utf-8').rstrip('=')

def _b64dec(data: str) -> bytes:
    pad = b'=' * (4 - (len(data) % 4))
    return base64.urlsafe_b64decode(data.encode('utf-8') + pad)

def create_jwt(payload: dict, expires_in: int = 3600) -> str:
    header = {"alg": "HS256", "typ": "JWT"}
    payload = payload.copy()
    payload["exp"] = int(time.time()) + expires_in
    
    header_b64 = _b64enc(json.dumps(header).encode('utf-8'))
    payload_b64 = _b64enc(json.dumps(payload).encode('utf-8'))
    
    msg = f"{header_b64}.{payload_b64}"
    sig = hmac.new(SECRET_KEY.encode(), msg.encode(), hashlib.sha256).digest()
    sig_b64 = _b64enc(sig)
    
    return f"{msg}.{sig_b64}"

def verify_jwt(token: str) -> dict:
    parts = token.split(".")
    if len(parts) != 3:
        raise ValueError("Invalid JWT format")
    
    msg = f"{parts[0]}.{parts[1]}"
    sig = _b64dec(parts[2])
    
    expected_sig = hmac.new(SECRET_KEY.encode(), msg.encode(), hashlib.sha256).digest()
    if not hmac.compare_digest(sig, expected_sig):
        raise ValueError("Invalid signature")
        
    payload = json.loads(_b64dec(parts[1]).decode('utf-8'))
    if payload.get("exp", 0) < time.time():
        raise ValueError("Token expired")
        
    return payload

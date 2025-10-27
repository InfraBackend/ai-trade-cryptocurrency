"""
Secure storage module for API credentials encryption
"""
import os
import base64
from typing import Optional, Tuple

try:
    from cryptography.fernet import Fernet
    from cryptography.hazmat.primitives import hashes
    from cryptography.hazmat.primitives.kdf.pbkdf2 import PBKDF2HMAC
    CRYPTO_AVAILABLE = True
except ImportError:
    CRYPTO_AVAILABLE = False
    print("[WARNING] cryptography library not available, using plain text storage")


class SecureStorage:
    """Secure storage for API credentials"""
    
    def __init__(self, password: str = None):
        self.password = password or self._get_default_password()
        self._fernet = None
        
        if CRYPTO_AVAILABLE:
            self._init_encryption()
    
    def _get_default_password(self) -> str:
        """Get default password from environment or generate one"""
        # Try to get from environment variable
        password = os.environ.get('TRADING_BOT_SECRET_KEY')
        
        if not password:
            # Generate a default password based on system info
            # This is not the most secure, but better than no encryption
            import platform
            import hashlib
            
            system_info = f"{platform.node()}-{platform.system()}-trading-bot"
            password = hashlib.sha256(system_info.encode()).hexdigest()[:32]
        
        return password
    
    def _init_encryption(self):
        """Initialize Fernet encryption"""
        try:
            # Derive key from password
            password_bytes = self.password.encode()
            salt = b'trading_bot_salt_2024'  # Fixed salt for consistency
            
            kdf = PBKDF2HMAC(
                algorithm=hashes.SHA256(),
                length=32,
                salt=salt,
                iterations=100000,
            )
            
            key = base64.urlsafe_b64encode(kdf.derive(password_bytes))
            self._fernet = Fernet(key)
            
        except Exception as e:
            print(f"[WARNING] Failed to initialize encryption: {e}")
            self._fernet = None
    
    def encrypt_credentials(self, api_key: str, secret_key: str, passphrase: str) -> str:
        """Encrypt API credentials"""
        if not CRYPTO_AVAILABLE or not self._fernet:
            # Fallback to base64 encoding (not secure, but better than plain text)
            credentials = f"{api_key}:{secret_key}:{passphrase}"
            return base64.b64encode(credentials.encode()).decode()
        
        try:
            credentials = f"{api_key}:{secret_key}:{passphrase}"
            encrypted = self._fernet.encrypt(credentials.encode())
            return base64.urlsafe_b64encode(encrypted).decode()
            
        except Exception as e:
            print(f"[ERROR] Failed to encrypt credentials: {e}")
            # Fallback to base64
            credentials = f"{api_key}:{secret_key}:{passphrase}"
            return base64.b64encode(credentials.encode()).decode()
    
    def decrypt_credentials(self, encrypted_data: str) -> Tuple[str, str, str]:
        """Decrypt API credentials"""
        if not encrypted_data:
            return "", "", ""
        
        try:
            if not CRYPTO_AVAILABLE or not self._fernet:
                # Simple base64 decoding
                try:
                    decoded = base64.b64decode(encrypted_data.encode()).decode('utf-8')
                    parts = decoded.split(':', 2)
                    if len(parts) == 3:
                        return parts[0], parts[1], parts[2]
                except Exception:
                    pass
                return "", "", ""
            
            # Try Fernet decryption first
            try:
                encrypted_bytes = base64.urlsafe_b64decode(encrypted_data.encode())
                decrypted = self._fernet.decrypt(encrypted_bytes)
                credentials = decrypted.decode('utf-8')
                parts = credentials.split(':', 2)
                if len(parts) == 3:
                    return parts[0], parts[1], parts[2]
            except Exception:
                # Fallback to base64 decoding
                try:
                    decoded = base64.b64decode(encrypted_data.encode()).decode('utf-8')
                    parts = decoded.split(':', 2)
                    if len(parts) == 3:
                        return parts[0], parts[1], parts[2]
                except Exception:
                    pass
            
            return "", "", ""
            
        except Exception as e:
            print(f"[WARNING] Credential decrypt failed: {e}")
            return "", "", ""
    
    def encrypt_single_value(self, value: str) -> str:
        """Encrypt a single value"""
        if not value:
            return ""
        
        if not CRYPTO_AVAILABLE or not self._fernet:
            return base64.b64encode(value.encode()).decode()
        
        try:
            encrypted = self._fernet.encrypt(value.encode())
            return base64.urlsafe_b64encode(encrypted).decode()
        except Exception as e:
            print(f"[ERROR] Failed to encrypt value: {e}")
            return base64.b64encode(value.encode()).decode()
    
    def decrypt_single_value(self, encrypted_value: str) -> str:
        """Decrypt a single value"""
        if not encrypted_value:
            return ""
        
        try:
            if not CRYPTO_AVAILABLE or not self._fernet:
                # Simple base64 decoding
                try:
                    return base64.b64decode(encrypted_value.encode()).decode('utf-8')
                except Exception:
                    return encrypted_value  # Return as-is if not base64
            
            # Try Fernet decryption first
            try:
                encrypted_bytes = base64.urlsafe_b64decode(encrypted_value.encode())
                decrypted = self._fernet.decrypt(encrypted_bytes)
                return decrypted.decode('utf-8')
            except Exception:
                # Fallback to base64 decoding
                try:
                    return base64.b64decode(encrypted_value.encode()).decode('utf-8')
                except Exception:
                    # If all fails, return the original value (might be plain text)
                    return encrypted_value
                
        except Exception as e:
            print(f"[WARNING] Decrypt failed, using original value: {e}")
            return encrypted_value


# Global instance
_secure_storage = None

def get_secure_storage() -> SecureStorage:
    """Get global secure storage instance"""
    global _secure_storage
    if _secure_storage is None:
        _secure_storage = SecureStorage()
    return _secure_storage
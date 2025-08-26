import asyncio
import hashlib
import hmac
import json
import random
import re
import string
import time
from typing import Dict, Optional, Tuple, Any, List
import logging
from cryptography.fernet import Fernet
from cryptography.hazmat.primitives import hashes
from cryptography.hazmat.primitives.kdf.pbkdf2 import PBKDF2HMAC
import base64
import os
from datetime import datetime, timedelta
import secrets

logger = logging.getLogger(__name__)

class SecurityConfig:
    """Security configuration constants"""
    # Rate limiting
    MAX_REQUESTS_PER_MINUTE = 30
    MAX_REQUESTS_PER_HOUR = 200
    MAX_LOGIN_ATTEMPTS = 5
    LOGIN_LOCKOUT_DURATION = 300  # 5 minutes
    
    # Captcha
    CAPTCHA_EXPIRY_SECONDS = 300  # 5 minutes
    MAX_CAPTCHA_ATTEMPTS = 3
    
    # Session
    SESSION_TIMEOUT_SECONDS = 3600  # 1 hour
    MAX_CONCURRENT_SESSIONS = 3
    
    # Wallet security
    PRIVATE_KEY_MIN_LENGTH = 80
    PRIVATE_KEY_MAX_LENGTH = 90
    ADDRESS_LENGTH = 44
    
    # Input validation
    MAX_USERNAME_LENGTH = 50
    MAX_MESSAGE_LENGTH = 500
    MAX_AMOUNT_DIGITS = 10
    
    # Encryption
    SALT_LENGTH = 32
    IV_LENGTH = 16

class RateLimiter:
    """Advanced rate limiter with multiple time windows"""
    
    def __init__(self):
        self.requests = {}
        self.failed_attempts = {}
        self.locked_users = {}
        
    async def allow_request(self, user_id: int, endpoint: str = "default") -> bool:
        """Check if user is allowed to make request"""
        current_time = time.time()
        
        # Check if user is locked out
        if await self._is_locked_out(user_id, current_time):
            return False
            
        # Initialize user tracking
        if user_id not in self.requests:
            self.requests[user_id] = {}
            
        if endpoint not in self.requests[user_id]:
            self.requests[user_id][endpoint] = {
                'minute': [],
                'hour': []
            }
            
        user_requests = self.requests[user_id][endpoint]
        
        # Clean old requests
        user_requests['minute'] = [t for t in user_requests['minute'] if current_time - t < 60]
        user_requests['hour'] = [t for t in user_requests['hour'] if current_time - t < 3600]
        
        # Check limits
        if len(user_requests['minute']) >= SecurityConfig.MAX_REQUESTS_PER_MINUTE:
            await self._record_failed_attempt(user_id)
            logger.warning(f"Rate limit exceeded (minute) for user {user_id}")
            return False
            
        if len(user_requests['hour']) >= SecurityConfig.MAX_REQUESTS_PER_HOUR:
            await self._record_failed_attempt(user_id)
            logger.warning(f"Rate limit exceeded (hour) for user {user_id}")
            return False
            
        # Record request
        user_requests['minute'].append(current_time)
        user_requests['hour'].append(current_time)
        
        return True
    
    async def _is_locked_out(self, user_id: int, current_time: float) -> bool:
        """Check if user is locked out"""
        if user_id in self.locked_users:
            unlock_time = self.locked_users[user_id]
            if current_time < unlock_time:
                return True
            else:
                del self.locked_users[user_id]
                
        return False
    
    async def _record_failed_attempt(self, user_id: int):
        """Record failed attempt and lock user if necessary"""
        current_time = time.time()
        
        if user_id not in self.failed_attempts:
            self.failed_attempts[user_id] = []
            
        # Clean old attempts
        self.failed_attempts[user_id] = [
            t for t in self.failed_attempts[user_id] 
            if current_time - t < 300  # 5 minutes
        ]
        
        # Add current attempt
        self.failed_attempts[user_id].append(current_time)
        
        # Lock user if too many attempts
        if len(self.failed_attempts[user_id]) >= SecurityConfig.MAX_LOGIN_ATTEMPTS:
            self.locked_users[user_id] = current_time + SecurityConfig.LOGIN_LOCKOUT_DURATION
            logger.warning(f"User {user_id} locked out due to too many failed attempts")
    
    async def reset_user_limits(self, user_id: int):
        """Reset rate limits for a user (admin function)"""
        if user_id in self.requests:
            del self.requests[user_id]
        if user_id in self.failed_attempts:
            del self.failed_attempts[user_id]
        if user_id in self.locked_users:
            del self.locked_users[user_id]

class CaptchaGenerator:
    """Secure captcha generator with multiple types"""
    
    def __init__(self):
        self.captcha_storage = {}
        self.attempt_counts = {}
        
    def generate(self, difficulty: str = "medium") -> Tuple[str, str]:
        """Generate captcha question and answer"""
        captcha_type = random.choice(['math', 'sequence', 'word'])
        
        if captcha_type == 'math':
            return self._generate_math_captcha(difficulty)
        elif captcha_type == 'sequence':
            return self._generate_sequence_captcha(difficulty)
        else:
            return self._generate_word_captcha(difficulty)
    
    def _generate_math_captcha(self, difficulty: str) -> Tuple[str, str]:
        """Generate math captcha"""
        if difficulty == "easy":
            a = random.randint(1, 10)
            b = random.randint(1, 10)
            operation = random.choice(['+', '-'])
        elif difficulty == "hard":
            a = random.randint(10, 50)
            b = random.randint(10, 50)
            operation = random.choice(['+', '-', '*'])
        else:  # medium
            a = random.randint(5, 25)
            b = random.randint(5, 25)
            operation = random.choice(['+', '-'])
        
        if operation == '+':
            answer = a + b
            question = f"Berapa {a} + {b}?"
        elif operation == '-':
            if a < b:
                a, b = b, a
            answer = a - b
            question = f"Berapa {a} - {b}?"
        else:  # multiplication
            answer = a * b
            question = f"Berapa {a} � {b}?"
            
        return question, str(answer)
    
    def _generate_sequence_captcha(self, difficulty: str) -> Tuple[str, str]:
        """Generate sequence captcha"""
        sequences = [
            ([2, 4, 6, 8], "10", "Lanjutkan: 2, 4, 6, 8, ?"),
            ([1, 3, 5, 7], "9", "Lanjutkan: 1, 3, 5, 7, ?"),
            ([5, 10, 15, 20], "25", "Lanjutkan: 5, 10, 15, 20, ?"),
            ([1, 4, 7, 10], "13", "Lanjutkan: 1, 4, 7, 10, ?")
        ]
        
        seq, answer, question = random.choice(sequences)
        return question, answer
    
    def _generate_word_captcha(self, difficulty: str) -> Tuple[str, str]:
        """Generate word captcha"""
        words = [
            ("TRADING", "Sebutkan huruf ke-3 dari kata TRADING"),
            ("SOLANA", "Sebutkan huruf terakhir dari kata SOLANA"),
            ("WALLET", "Berapa jumlah huruf dalam kata WALLET?"),
            ("CRYPTO", "Sebutkan huruf pertama dari kata CRYPTO")
        ]
        
        word, question = random.choice(words)
        
        if "huruf ke-3" in question:
            answer = word[2]
        elif "huruf terakhir" in question:
            answer = word[-1]
        elif "jumlah huruf" in question:
            answer = str(len(word))
        else:  # huruf pertama
            answer = word[0]
            
        return question, answer
    
    async def store_captcha(self, user_id: int, answer: str, db_instance = None) -> bool:
        """Store captcha answer for user"""
        try:
            current_time = time.time()
            
            # Store in memory for quick access
            self.captcha_storage[user_id] = {
                'answer': answer.upper().strip(),
                'expires_at': current_time + SecurityConfig.CAPTCHA_EXPIRY_SECONDS,
                'attempts': 0
            }
            
            # Also store in MongoDB if db instance provided
            if db_instance:
                await db_instance.store_captcha(user_id, answer.upper().strip())
            
            return True
        except Exception as e:
            logger.error(f"Error storing captcha: {e}")
            return False
    
    async def verify_captcha(self, user_id: int, user_answer: str, db_instance = None) -> bool:
        """Verify captcha answer"""
        try:
            # First try memory storage
            if user_id in self.captcha_storage:
                captcha_data = self.captcha_storage[user_id]
                current_time = time.time()
                
                # Check expiry
                if current_time > captcha_data['expires_at']:
                    del self.captcha_storage[user_id]
                    return False
                
                # Check attempts
                captcha_data['attempts'] += 1
                if captcha_data['attempts'] > SecurityConfig.MAX_CAPTCHA_ATTEMPTS:
                    del self.captcha_storage[user_id]
                    return False
                
                # Verify answer
                if captcha_data['answer'] == user_answer.upper().strip():
                    del self.captcha_storage[user_id]
                    return True
                    
                return False
            
            # Fallback to MongoDB if available
            elif db_instance:
                return await db_instance.verify_captcha(user_id, user_answer.upper().strip())
            
            return False
            
        except Exception as e:
            logger.error(f"Error verifying captcha: {e}")
            return False
    
    async def generate_captcha(self, user_id: int) -> Optional[Dict[str, str]]:
        """Generate and store captcha for user"""
        try:
            question, answer = self.generate()
            success = await self.store_captcha(user_id, answer)
            
            if success:
                return {
                    'question': question,
                    'answer': answer  # For testing only, remove in production
                }
            return None
            
        except Exception as e:
            logger.error(f"Error generating captcha: {e}")
            return None

class InputValidator:
    """Comprehensive input validation"""
    
    @staticmethod
    def validate_solana_address(address: str) -> bool:
        """Validate Solana wallet address"""
        if not address or not isinstance(address, str):
            return False
            
        # Check length
        if len(address) != SecurityConfig.ADDRESS_LENGTH:
            return False
            
        # Check base58 format
        base58_pattern = r'^[1-9A-HJ-NP-Za-km-z]{44}$'
        return bool(re.match(base58_pattern, address))
    
    @staticmethod
    def validate_private_key(private_key: str) -> bool:
        """Validate Solana private key"""
        if not private_key or not isinstance(private_key, str):
            return False
            
        # Check length
        if not (SecurityConfig.PRIVATE_KEY_MIN_LENGTH <= len(private_key) <= SecurityConfig.PRIVATE_KEY_MAX_LENGTH):
            return False
            
        # Check base58 format
        base58_pattern = r'^[1-9A-HJ-NP-Za-km-z]+$'
        return bool(re.match(base58_pattern, private_key))
    
    @staticmethod
    def validate_amount(amount_str: str, max_decimals: int = 8) -> Tuple[bool, float]:
        """Validate trading amount"""
        try:
            if not amount_str or not isinstance(amount_str, str):
                return False, 0.0
                
            # Remove whitespace
            amount_str = amount_str.strip()
            
            # Check for valid number format
            amount_pattern = r'^\d{1,' + str(SecurityConfig.MAX_AMOUNT_DIGITS) + r'}(\.\d{1,' + str(max_decimals) + r'})?$'
            if not re.match(amount_pattern, amount_str):
                return False, 0.0
            
            amount = float(amount_str)
            
            # Check reasonable bounds
            if amount <= 0 or amount > 1000000:  # Max 1M SOL
                return False, 0.0
                
            return True, amount
            
        except (ValueError, OverflowError):
            return False, 0.0
    
    @staticmethod
    def validate_percentage(percent_str: str) -> Tuple[bool, float]:
        """Validate percentage input"""
        try:
            if not percent_str or not isinstance(percent_str, str):
                return False, 0.0
                
            percent_str = percent_str.strip().replace('%', '')
            
            if not re.match(r'^\d{1,3}(\.\d{1,2})?$', percent_str):
                return False, 0.0
            
            percent = float(percent_str)
            
            if percent < 0 or percent > 10000:  # Max 10000%
                return False, 0.0
                
            return True, percent
            
        except (ValueError, OverflowError):
            return False, 0.0
    
    @staticmethod
    def sanitize_message(message: str) -> str:
        """Sanitize user message input"""
        if not message or not isinstance(message, str):
            return ""
            
        # Truncate length
        message = message[:SecurityConfig.MAX_MESSAGE_LENGTH]
        
        # Remove potentially dangerous characters
        dangerous_chars = ['<', '>', '"', "'", '&', '`']
        for char in dangerous_chars:
            message = message.replace(char, '')
            
        return message.strip()
    
    @staticmethod
    def validate_username(username: str) -> bool:
        """Validate username format"""
        if not username or not isinstance(username, str):
            return False
            
        if len(username) > SecurityConfig.MAX_USERNAME_LENGTH:
            return False
            
        # Allow alphanumeric, underscore, dash
        pattern = r'^[a-zA-Z0-9_-]+$'
        return bool(re.match(pattern, username))

class CryptoUtils:
    """Cryptographic utilities for secure data handling"""
    
    def __init__(self, master_key: Optional[str] = None):
        self.master_key = master_key or os.getenv('ENCRYPTION_KEY', self._generate_key())
        
    def _generate_key(self) -> str:
        """Generate a new encryption key"""
        return base64.urlsafe_b64encode(os.urandom(32)).decode()
    
    def _derive_key(self, password: str, salt: bytes) -> bytes:
        """Derive encryption key from password and salt"""
        kdf = PBKDF2HMAC(
            algorithm=hashes.SHA256(),
            length=32,
            salt=salt,
            iterations=100000,
        )
        return base64.urlsafe_b64encode(kdf.derive(password.encode()))
    
    async def encrypt_private_key(self, private_key: str, user_id: int) -> Dict[str, str]:
        """Encrypt private key with user-specific salt"""
        try:
            # Generate salt
            salt = secrets.token_bytes(SecurityConfig.SALT_LENGTH)
            
            # Derive key
            derived_key = self._derive_key(f"{self.master_key}:{user_id}", salt)
            fernet = Fernet(derived_key)
            
            # Encrypt
            encrypted_data = fernet.encrypt(private_key.encode())
            
            return {
                'encrypted_data': base64.urlsafe_b64encode(encrypted_data).decode(),
                'salt': base64.urlsafe_b64encode(salt).decode(),
                'algorithm': 'fernet-pbkdf2'
            }
            
        except Exception as e:
            logger.error(f"Error encrypting private key: {e}")
            raise
    
    async def decrypt_private_key(self, encrypted_data: Dict[str, str], user_id: int) -> str:
        """Decrypt private key"""
        try:
            # Decode salt
            salt = base64.urlsafe_b64decode(encrypted_data['salt'])
            
            # Derive key
            derived_key = self._derive_key(f"{self.master_key}:{user_id}", salt)
            fernet = Fernet(derived_key)
            
            # Decrypt
            encrypted_bytes = base64.urlsafe_b64decode(encrypted_data['encrypted_data'])
            decrypted_data = fernet.decrypt(encrypted_bytes)
            
            return decrypted_data.decode()
            
        except Exception as e:
            logger.error(f"Error decrypting private key: {e}")
            raise
    
    def generate_secure_token(self, length: int = 32) -> str:
        """Generate secure random token"""
        return secrets.token_urlsafe(length)
    
    def hash_password(self, password: str, salt: Optional[str] = None) -> Tuple[str, str]:
        """Hash password with salt"""
        if salt is None:
            salt = secrets.token_hex(16)
        else:
            salt = salt
            
        hashed = hashlib.pbkdf2_hmac('sha256', password.encode(), salt.encode(), 100000)
        return base64.b64encode(hashed).decode(), salt
    
    def verify_password(self, password: str, hashed_password: str, salt: str) -> bool:
        """Verify password against hash"""
        try:
            test_hash, _ = self.hash_password(password, salt)
            return hmac.compare_digest(test_hash, hashed_password)
        except Exception:
            return False

class SessionManager:
    """Secure session management"""
    
    def __init__(self):
        self.sessions = {}
        self.user_sessions = {}
        
    async def create_session(self, user_id: int, additional_data: Optional[Dict] = None) -> str:
        """Create new session for user"""
        try:
            # Check concurrent sessions limit
            user_session_count = len(self.user_sessions.get(user_id, []))
            if user_session_count >= SecurityConfig.MAX_CONCURRENT_SESSIONS:
                # Remove oldest session
                await self._cleanup_oldest_session(user_id)
            
            # Generate session token
            session_token = secrets.token_urlsafe(32)
            
            # Create session data
            session_data = {
                'user_id': user_id,
                'created_at': datetime.utcnow(),
                'expires_at': datetime.utcnow() + timedelta(seconds=SecurityConfig.SESSION_TIMEOUT_SECONDS),
                'ip_address': additional_data.get('ip_address') if additional_data else None,
                'user_agent': additional_data.get('user_agent') if additional_data else None,
                'last_activity': datetime.utcnow()
            }
            
            # Store session
            self.sessions[session_token] = session_data
            
            # Track user sessions
            if user_id not in self.user_sessions:
                self.user_sessions[user_id] = []
            self.user_sessions[user_id].append(session_token)
            
            logger.info(f"Session created for user {user_id}: {session_token[:8]}...")
            return session_token
            
        except Exception as e:
            logger.error(f"Error creating session: {e}")
            raise
    
    async def validate_session(self, session_token: str) -> Optional[Dict]:
        """Validate and return session data"""
        try:
            if session_token not in self.sessions:
                return None
                
            session_data = self.sessions[session_token]
            
            # Check expiry
            if datetime.utcnow() > session_data['expires_at']:
                await self.revoke_session(session_token)
                return None
            
            # Update last activity
            session_data['last_activity'] = datetime.utcnow()
            
            return session_data
            
        except Exception as e:
            logger.error(f"Error validating session: {e}")
            return None
    
    async def revoke_session(self, session_token: str):
        """Revoke specific session"""
        try:
            if session_token in self.sessions:
                user_id = self.sessions[session_token]['user_id']
                
                # Remove from sessions
                del self.sessions[session_token]
                
                # Remove from user sessions
                if user_id in self.user_sessions:
                    self.user_sessions[user_id] = [
                        token for token in self.user_sessions[user_id] 
                        if token != session_token
                    ]
                    
                logger.info(f"Session revoked: {session_token[:8]}...")
                
        except Exception as e:
            logger.error(f"Error revoking session: {e}")
    
    async def revoke_all_user_sessions(self, user_id: int):
        """Revoke all sessions for a user"""
        try:
            if user_id in self.user_sessions:
                for session_token in self.user_sessions[user_id]:
                    if session_token in self.sessions:
                        del self.sessions[session_token]
                        
                del self.user_sessions[user_id]
                logger.info(f"All sessions revoked for user {user_id}")
                
        except Exception as e:
            logger.error(f"Error revoking user sessions: {e}")
    
    async def _cleanup_oldest_session(self, user_id: int):
        """Remove oldest session for user"""
        if user_id not in self.user_sessions:
            return
            
        user_session_tokens = self.user_sessions[user_id]
        if not user_session_tokens:
            return
            
        # Find oldest session
        oldest_token = None
        oldest_time = datetime.utcnow()
        
        for token in user_session_tokens:
            if token in self.sessions:
                session_time = self.sessions[token]['created_at']
                if session_time < oldest_time:
                    oldest_time = session_time
                    oldest_token = token
        
        if oldest_token:
            await self.revoke_session(oldest_token)
    
    async def cleanup_expired_sessions(self):
        """Clean up expired sessions (call periodically)"""
        try:
            current_time = datetime.utcnow()
            expired_tokens = []
            
            for token, session_data in self.sessions.items():
                if current_time > session_data['expires_at']:
                    expired_tokens.append(token)
            
            for token in expired_tokens:
                await self.revoke_session(token)
                
            logger.info(f"Cleaned up {len(expired_tokens)} expired sessions")
            
        except Exception as e:
            logger.error(f"Error cleaning up sessions: {e}")

class SecurityLogger:
    """Security event logging"""
    
    def __init__(self):
        self.security_logger = logging.getLogger('security')
        
    def log_auth_attempt(self, user_id: int, success: bool, ip_address: str = None):
        """Log authentication attempt"""
        status = "SUCCESS" if success else "FAILED"
        self.security_logger.info(
            f"AUTH_{status}: user_id={user_id}, ip={ip_address}, time={datetime.utcnow()}"
        )
    
    def log_rate_limit_hit(self, user_id: int, endpoint: str, ip_address: str = None):
        """Log rate limit violation"""
        self.security_logger.warning(
            f"RATE_LIMIT: user_id={user_id}, endpoint={endpoint}, ip={ip_address}, time={datetime.utcnow()}"
        )
    
    def log_suspicious_activity(self, user_id: int, activity: str, details: Dict = None):
        """Log suspicious activity"""
        self.security_logger.critical(
            f"SUSPICIOUS: user_id={user_id}, activity={activity}, details={details}, time={datetime.utcnow()}"
        )
    
    def log_crypto_operation(self, user_id: int, operation: str, success: bool):
        """Log cryptographic operations"""
        status = "SUCCESS" if success else "FAILED"
        self.security_logger.info(
            f"CRYPTO_{status}: user_id={user_id}, operation={operation}, time={datetime.utcnow()}"
        )
    
    def log_transaction_attempt(self, user_id: int, transaction_type: str, amount: float, success: bool):
        """Log trading transaction attempts"""
        status = "SUCCESS" if success else "FAILED"
        self.security_logger.info(
            f"TRANSACTION_{status}: user_id={user_id}, type={transaction_type}, amount={amount}, time={datetime.utcnow()}"
        )

# Utility functions for common security checks
def is_safe_telegram_user_id(user_id: int) -> bool:
    """Check if Telegram user ID is valid"""
    return isinstance(user_id, int) and 1 <= user_id <= 999999999999

def generate_anti_csrf_token() -> str:
    """Generate anti-CSRF token"""
    return secrets.token_urlsafe(32)

def constant_time_compare(a: str, b: str) -> bool:
    """Constant time string comparison to prevent timing attacks"""
    return hmac.compare_digest(a, b)

# Initialize global instances
rate_limiter = RateLimiter()
captcha_generator = CaptchaGenerator()
crypto_utils = CryptoUtils()
session_manager = SessionManager()
security_logger = SecurityLogger()

# Export main classes and functions
__all__ = [
    'SecurityConfig',
    'RateLimiter', 
    'CaptchaGenerator',
    'InputValidator',
    'CryptoUtils',
    'SessionManager',
    'SecurityLogger',
    'is_safe_telegram_user_id',
    'generate_anti_csrf_token',
    'constant_time_compare',
    'rate_limiter',
    'captcha_generator',
    'crypto_utils',
    'session_manager',
    'security_logger'
]
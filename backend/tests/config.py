# EvoLoop Test Suite Configuration
# This file contains test parameters and fixtures

import os
from dataclasses import dataclass

@dataclass
class TestConfig:
    """Test environment configuration."""
    # API Base URL
    API_BASE_URL: str = os.getenv("TEST_API_URL", "http://localhost:8000")
    
    # Project Configuration
    PROJECT_NAME: str = "dazui"
    PROJECT_PATH: str = "/Users/huangjinhuan/项目/dazui"
    PROJECT_ID: int = 7
    
    # User Credentials
    USERNAME: str = "preterchan"
    PASSWORD: str = "hellomylife"
    AUTH_TOKEN: str = "MDAwMDAwMDAwMJmvg62RumKdio-wnJO4tM6DoKfUf9OurL2KfpO-jpthlY1qpYDNoKx-sb9qgKWklYN6q9iCqaufyHt608eluJeYfaWtkbZ6an2LyWiBpbiYgrC72oOukXA"
    
    # Test Timeouts
    SSE_TIMEOUT: int = 60  # seconds
    API_TIMEOUT: int = 60  # seconds
    AGENT_TIMEOUT: int = 180  # seconds
    
    # Test Thread IDs (will be generated dynamically)
    @staticmethod
    def generate_thread_id() -> str:
        import uuid
        return f"test-{uuid.uuid4().hex[:12]}"

# Singleton instance
config = TestConfig()

# Headers for authenticated requests
def get_auth_headers() -> dict:
    return {
        "Authorization": f"Bearer {config.AUTH_TOKEN}",
        "Content-Type": "application/json"
    }

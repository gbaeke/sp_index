import sys
import logging
import requests
from dotenv import load_dotenv

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    datefmt="%H:%M:%S"
)
logger = logging.getLogger(__name__)

def load_base_env():
    """Load environment variables from .env file."""
    load_dotenv()

def validate_config(config, required_fields):
    """Validate that required fields are present in the config."""
    missing_fields = [field for field in required_fields if not config.get(field)]
    if missing_fields:
        logger.error(f"Missing required configuration: {', '.join(missing_fields)}")
        sys.exit(1)

def make_request(config, method, path, body=None):
    """Make an HTTP request to Azure AI Search with error handling."""
    url = f"{config['search_endpoint']}{path}"
    params = {"api-version": config["api_version"]}
    headers = {
        "api-key": config["api_key"],
        "Content-Type": "application/json",
    }
    
    try:
        response = requests.request(
            method=method,
            url=url,
            params=params,
            headers=headers,
            json=body,
            timeout=30  # Add timeout
        )
        return response
    except requests.exceptions.RequestException as e:
        logger.error(f"Request failed: {e}")
        # Return a dummy response object with error status for compatibility
        class ErrorResponse:
            status_code = 500
            text = str(e)
            
            def json(self):
                return {"error": self.text}
        return ErrorResponse()

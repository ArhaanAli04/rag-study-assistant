
from typing import Dict

class UserFriendlyError:
    """Convert technical errors to user-friendly messages"""
    
    ERROR_MESSAGES = {
        "circuit_breaker": "I'm experiencing high load right now. Please try again in a moment.",
        "api_timeout": "The request is taking longer than expected. Please try again.",
        "auth_expired": "Your session has expired. Please log in again.",
        "no_context": "I couldn't find relevant information in your documents. Try asking in a different way.",
        "rate_limit": "Too many requests. Please wait a moment before trying again.",
        "network_error": "I'm having trouble connecting. Please check your internet connection.",
        "unknown": "Something went wrong. Please try again or contact support if the issue persists."
    }
    
    @staticmethod
    def get_message(error_type: str, details: str = None) -> Dict:
        """Get user-friendly error message"""
        message = UserFriendlyError.ERROR_MESSAGES.get(error_type, UserFriendlyError.ERROR_MESSAGES["unknown"])
        
        return {
            "error": message,
            "type": error_type,
            "details": details if details else None,
            "action": UserFriendlyError._get_action(error_type)
        }
    
    @staticmethod
    def _get_action(error_type: str) -> str:
        """Suggest user action"""
        actions = {
            "circuit_breaker": "Wait 1-2 minutes",
            "api_timeout": "Try a simpler question",
            "auth_expired": "Log in again",
            "no_context": "Rephrase your question or upload relevant documents",
            "rate_limit": "Wait 30 seconds",
            "network_error": "Check your connection",
            "unknown": "Refresh the page"
        }
        return actions.get(error_type, "Try again")
    
    @staticmethod
    def classify_error(exception: Exception) -> str:
        """Classify exception type"""
        error_msg = str(exception).lower()
        
        if "circuit breaker" in error_msg:
            return "circuit_breaker"
        elif "timeout" in error_msg:
            return "api_timeout"
        elif "rate limit" in error_msg or "429" in error_msg:
            return "rate_limit"
        elif "network" in error_msg or "connection" in error_msg:
            return "network_error"
        elif "llm" in error_msg or "gemini" in error_msg:
            return "llm_error"
        else:
            return "unknown"

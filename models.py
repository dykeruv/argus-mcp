"""
Model providers with retry logic and fallback support
"""

import asyncio
import httpx
import sys
from datetime import datetime
from typing import Dict, Any, Optional, List
from config import (
    MODELS, DEFAULT_TEMPERATURE, DEFAULT_MAX_TOKENS,
    RETRY_ATTEMPTS, RETRY_MIN_WAIT, RETRY_MAX_WAIT, RETRY_STATUS_CODES,
    get_fallback_models
)


# Error tracking for diagnostics
_error_log: List[Dict[str, Any]] = []


def log_error(model: str, error_type: str, details: str, status_code: int = None):
    """Log error for diagnostics"""
    entry = {
        "timestamp": datetime.now().isoformat(),
        "model": model,
        "error_type": error_type,
        "details": details[:500],  # Truncate long errors
        "status_code": status_code
    }
    _error_log.append(entry)
    # Keep only last 50 errors
    if len(_error_log) > 50:
        _error_log.pop(0)
    # Also print to stderr for debugging
    print(f"[ARGUS ERROR] {model}: {error_type} - {details[:200]}", file=sys.stderr)


def get_error_log() -> List[Dict[str, Any]]:
    """Get recent errors for diagnostics"""
    return _error_log.copy()


def clear_error_log():
    """Clear error log"""
    _error_log.clear()


def format_error_for_user(errors: List[Dict[str, Any]]) -> str:
    """Format errors into human-readable message"""
    if not errors:
        return "No errors recorded."
    
    lines = ["## Recent Errors\n"]
    for err in errors[-5:]:  # Last 5 errors
        status = f" (HTTP {err['status_code']})" if err.get('status_code') else ""
        lines.append(f"- **{err['model']}**: {err['error_type']}{status}")
        lines.append(f"  - {err['details'][:150]}")
    
    lines.append("\n## Possible Causes\n")
    
    # Analyze errors
    has_401 = any(e.get('status_code') == 401 for e in errors)
    has_429 = any(e.get('status_code') == 429 for e in errors)
    has_timeout = any('timeout' in e.get('details', '').lower() for e in errors)
    has_connection = any('connect' in e.get('details', '').lower() for e in errors)
    
    if has_401:
        lines.append("- **Invalid API Key**: Check your `.env` file. Keys may be expired or incorrect.")
    if has_429:
        lines.append("- **Rate Limited**: You've hit the API rate limit. Wait a few minutes.")
    if has_timeout:
        lines.append("- **Timeout**: API is slow or overloaded. Try again later or reduce payload size.")
    if has_connection:
        lines.append("- **Connection Error**: Network issue. Check your internet connection.")
    
    if not (has_401 or has_429 or has_timeout or has_connection):
        lines.append("- Check API provider status pages (z.ai, OpenRouter)")
        lines.append("- Verify API keys are valid and have credits")
    
    return "\n".join(lines)


class ModelProvider:
    """Base class for model providers"""
    
    def __init__(self, model_key: str):
        if model_key not in MODELS:
            raise ValueError(f"Unknown model: {model_key}")
        
        self.config = MODELS[model_key]
        if not self.config["enabled"]:
            raise ValueError(f"Model {model_key} is not enabled (missing API key)")
        
        self.model_key = model_key
    
    async def _call_api_with_retry(
        self,
        messages: list[dict],
        temperature: float = DEFAULT_TEMPERATURE,
        max_tokens: int = DEFAULT_MAX_TOKENS
    ) -> Dict[str, Any]:
        """Вызывает API с retry-логикой"""
        
        last_error = None
        
        for attempt in range(RETRY_ATTEMPTS):
            try:
                result = await self._call_api(messages, temperature, max_tokens)
                return result
            
            except httpx.HTTPStatusError as e:
                last_error = e
                
                # Retry только для определённых статусов
                if e.response.status_code not in RETRY_STATUS_CODES:
                    raise
                
                # Экспоненциальная задержка
                if attempt < RETRY_ATTEMPTS - 1:
                    wait_time = min(RETRY_MIN_WAIT * (2 ** attempt), RETRY_MAX_WAIT)
                    await asyncio.sleep(wait_time)
            
            except Exception as e:
                last_error = e
                # Для других ошибок не делаем retry
                raise
        
        # Если все попытки исчерпаны
        raise last_error
    
    async def _call_api(
        self,
        messages: list[dict],
        temperature: float,
        max_tokens: int
    ) -> Dict[str, Any]:
        """Вызывает API (должен быть переопределён в подклассах)"""
        
        timeout = self.config.get("timeout", 60)
        
        async with httpx.AsyncClient(timeout=timeout) as client:
            headers = {
                "Authorization": f"Bearer {self.config['api_key']}",
                "Content-Type": "application/json"
            }
            
            # Для OpenRouter добавляем дополнительные заголовки
            if self.config['provider'] == 'openrouter':
                headers["HTTP-Referer"] = "https://windsurf-mcp-verify-code"
                headers["X-Title"] = "Windsurf Code Verifier"
            
            response = await client.post(
                f"{self.config['base_url']}/chat/completions",
                headers=headers,
                json={
                    "model": self.config['model_id'],
                    "messages": messages,
                    "temperature": temperature,
                    "max_tokens": max_tokens
                }
            )
            
            response.raise_for_status()
            return response.json()
    
    async def verify_code(
        self,
        system_prompt: str,
        user_message: str
    ) -> Dict[str, Any]:
        """Проверяет код через модель"""
        
        messages = [
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": user_message}
        ]
        
        try:
            data = await self._call_api_with_retry(messages)
            
            verdict = data["choices"][0]["message"]["content"]
            
            return {
                "success": True,
                "verdict": verdict,
                "model": self.config['name'],
                "model_key": self.model_key,
                "tokens_used": data.get("usage", {}),
                "cost": self._calculate_cost(data.get("usage", {}))
            }
        
        except httpx.HTTPStatusError as e:
            error_msg = f"API Error: {e.response.status_code} - {e.response.text[:300]}"
            log_error(
                model=self.model_key,
                error_type="HTTP Error",
                details=error_msg,
                status_code=e.response.status_code
            )
            return {
                "success": False,
                "error": error_msg,
                "error_code": e.response.status_code,
                "model": self.config['name'],
                "model_key": self.model_key
            }
        
        except httpx.TimeoutException as e:
            error_msg = f"Request timed out after {self.config.get('timeout', 60)}s"
            log_error(
                model=self.model_key,
                error_type="Timeout",
                details=error_msg
            )
            return {
                "success": False,
                "error": error_msg,
                "error_code": "TIMEOUT",
                "model": self.config['name'],
                "model_key": self.model_key
            }
        
        except httpx.ConnectError as e:
            error_msg = f"Connection failed: {str(e)}"
            log_error(
                model=self.model_key,
                error_type="Connection Error",
                details=error_msg
            )
            return {
                "success": False,
                "error": error_msg,
                "error_code": "CONNECTION_ERROR",
                "model": self.config['name'],
                "model_key": self.model_key
            }
        
        except Exception as e:
            error_msg = f"{type(e).__name__}: {str(e)}"
            log_error(
                model=self.model_key,
                error_type=type(e).__name__,
                details=error_msg
            )
            return {
                "success": False,
                "error": error_msg,
                "model": self.config['name'],
                "model_key": self.model_key
            }
    
    def _calculate_cost(self, usage: dict) -> float:
        """Рассчитывает стоимость запроса"""
        if not usage:
            return 0.0
        
        total_tokens = usage.get("total_tokens", 0)
        cost_per_1k = self.config.get("cost_per_1k_tokens", 0.0)
        
        return (total_tokens / 1000) * cost_per_1k


class ModelManager:
    """Управляет моделями и fallback логикой"""
    
    def __init__(self):
        self._providers: Dict[str, ModelProvider] = {}
    
    def get_provider(self, model_key: str) -> ModelProvider:
        """Получает провайдер для модели"""
        if model_key not in self._providers:
            self._providers[model_key] = ModelProvider(model_key)
        return self._providers[model_key]
    
    async def verify_with_fallback(
        self,
        system_prompt: str,
        user_message: str,
        primary_model: str
    ) -> Dict[str, Any]:
        """Проверяет код с fallback на другие модели при ошибке"""
        
        errors_collected = []
        
        # Пробуем основную модель
        try:
            provider = self.get_provider(primary_model)
            result = await provider.verify_code(system_prompt, user_message)
            
            if result["success"]:
                return result
            else:
                errors_collected.append({
                    "model": primary_model,
                    "error": result.get("error", "Unknown error"),
                    "error_code": result.get("error_code")
                })
        
        except Exception as e:
            error_msg = f"{type(e).__name__}: {str(e)}"
            log_error(primary_model, "Provider Error", error_msg)
            errors_collected.append({
                "model": primary_model,
                "error": error_msg
            })
        
        # Если основная модель не сработала, пробуем fallback
        fallback_models = get_fallback_models(exclude=primary_model)
        
        for model_key in fallback_models:
            try:
                provider = self.get_provider(model_key)
                result = await provider.verify_code(system_prompt, user_message)
                
                if result["success"]:
                    # Добавляем информацию о fallback
                    result["fallback_used"] = True
                    result["primary_model_failed"] = primary_model
                    return result
                else:
                    errors_collected.append({
                        "model": model_key,
                        "error": result.get("error", "Unknown error"),
                        "error_code": result.get("error_code")
                    })
            
            except Exception as e:
                error_msg = f"{type(e).__name__}: {str(e)}"
                log_error(model_key, "Provider Error", error_msg)
                errors_collected.append({
                    "model": model_key,
                    "error": error_msg
                })
                continue
        
        # Если все модели не сработали - формируем детальное сообщение
        error_details = "\n".join([
            f"  - {e['model']}: {e['error'][:100]}" for e in errors_collected
        ])
        
        # Анализируем типы ошибок для рекомендаций
        recommendations = []
        error_codes = [e.get("error_code") for e in errors_collected if e.get("error_code")]
        error_texts = " ".join([e.get("error", "") for e in errors_collected]).lower()
        
        if 401 in error_codes:
            recommendations.append("🔑 Check API keys in `.env` file")
        if 429 in error_codes:
            recommendations.append("⏳ Rate limited - wait a few minutes")
        if "timeout" in error_texts:
            recommendations.append("⏱️ Timeout - try smaller code or wait")
        if "connect" in error_texts:
            recommendations.append("🌐 Network error - check connection")
        if not recommendations:
            recommendations.append("🔍 Check API provider status pages")
            recommendations.append("💳 Verify API keys have credits")
        
        return {
            "success": False,
            "error": f"All models failed. Primary: {primary_model}, Fallbacks: {fallback_models}",
            "error_details": error_details,
            "recommendations": recommendations,
            "errors": errors_collected,
            "model": "None",
            "model_key": None
        }


# Глобальный экземпляр менеджера
_manager = ModelManager()


def get_model_manager() -> ModelManager:
    """Возвращает глобальный экземпляр менеджера моделей"""
    return _manager

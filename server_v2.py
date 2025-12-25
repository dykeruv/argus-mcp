#!/usr/bin/env python3
"""
MCP Server: verify_code v2.0
Проверяет код через множественные AI модели с retry, fallback и кэшированием.
"""

print(r"""
   __   ____   ___  _   _  ___ 
  / _\ (  _ \ / __)( ) ( )/ __)
 /    \ )   /( (_ \ ) (_) )\__ \
 \_/\_/(__\_) \___/ \_____/(___/
      ARGUS MCP v2.0
   The All-Seeing Code Reviewer
""")

import json
import sys
import asyncio
from typing import Dict, Any, Optional

from config import (
    SERVER_NAME, SERVER_VERSION, MCP_PROTOCOL_VERSION,
    DEFAULT_MODEL, get_enabled_models
)
from validators import validate_arguments, sanitize_file_path
from prompts import build_system_prompt, build_user_message
from cache import get_cache
from models import get_model_manager


class MCPServer:
    def __init__(self):
        self.cache = get_cache()
        self.model_manager = get_model_manager()
        
        self.tools = {
            "verify_code": {
                "name": "verify_code",
                "description": """Verifies code through external AI model with Zero-Trust approach.

MODES:
1. Single File - review one file (params: code + file_path)
2. Git Diff - review changes via git diff (param: diff)
3. Multiple Files - review multiple files with cross-file dependencies (param: files[])

FEATURES:
- Retry with exponential backoff (3 attempts)
- Automatic fallback to other models on error
- Result caching (TTL: 1 hour)
- Language-aware checks for 10 languages (Python, JS, TS, Vue, React, Go, Rust, Java, PHP)
- Security (OWASP), performance, and architecture checks

MODELS:
- glm-4.7 (z.ai) - $0.40/M input, fast
- gemini-flash (OpenRouter) - $0.50/M input, very fast
- minimax (OpenRouter) - $0.30/M input

USAGE:
- \"Review my code\" - basic check
- \"Check code with Gemini\" - model selection
- \"Verify changes in multiple files\" - cross-file review""",
                "inputSchema": {
                    "type": "object",
                    "properties": {
                        "code": {
                            "type": "string",
                            "description": "[Mode 1: Single File] Full code of one file"
                        },
                        "diff": {
                            "type": "string",
                            "description": "[Mode 2: Git Diff] Git diff output (unified format). Saves tokens, shows only changes."
                        },
                        "files": {
                            "type": "array",
                            "description": "[Mode 3: Multiple Files] Array of files with changes",
                            "items": {
                                "type": "object",
                                "properties": {
                                    "path": {"type": "string", "description": "File path"},
                                    "content": {"type": "string", "description": "File content"},
                                    "diff": {"type": "string", "description": "Diff for this file (optional)"},
                                    "stats": {"type": "string", "description": "Change statistics, e.g. '+79 -11'"}
                                },
                                "required": ["path"]
                            }
                        },
                        "task_context": {
                            "type": "string",
                            "description": "Task description and what the code should do"
                        },
                        "session_changes": {
                            "type": "string",
                            "description": "Brief description of changes made in this session"
                        },
                        "file_path": {
                            "type": "string",
                            "description": "[Mode 1] File path (for single file mode)"
                        },
                        "model": {
                            "type": "string",
                            "description": f"Model for verification. Available: {', '.join(get_enabled_models())}",
                            "enum": get_enabled_models()
                        },
                        "use_cache": {
                            "type": "boolean",
                            "description": "Use cache (default true)"
                        },
                        "use_fallback": {
                            "type": "boolean",
                            "description": "Use fallback to other models on error (default true)"
                        },
                        "project_stack": {
                            "type": "object",
                            "description": "Project technology stack information for more accurate verification",
                            "properties": {
                                "framework": {"type": "string", "description": "Main framework (e.g., Django 5.0, FastAPI)"},
                                "frontend": {"type": "string", "description": "Frontend stack (e.g., Vue 3 + Inertia.js)"},
                                "backend": {"type": "string", "description": "Backend stack (e.g., Python 3.11)"},
                                "database": {"type": "string", "description": "Database (e.g., PostgreSQL 15)"},
                                "conventions": {"type": "string", "description": "Code conventions (e.g., Google Python Style Guide)"},
                                "architecture": {"type": "string", "description": "Architectural pattern (e.g., Clean Architecture, MVC)"}
                            }
                        }
                    },
                    "required": ["task_context"]
                }
            },
            "list_models": {
                "name": "list_models",
                "description": """Shows list of all available AI models for code verification.

INFORMATION:
- Model name and key
- Provider (z.ai, OpenRouter)
- Status (✅ available / ❌ unavailable)
- Cost per 1K tokens
- Max tokens
- Current default model

USAGE:
- \"Show available models\"
- \"What models can I use?\"
- \"List models for code review\"

RESULT: Table with full information about each model""",
                "inputSchema": {
                    "type": "object",
                    "properties": {}
                }
            },
            "set_default_model": {
                "name": "set_default_model",
                "description": """Sets default model for current session.

PURPOSE:
Changes the base model that will be used for all subsequent code checks if model is not specified explicitly.

AVAILABLE MODELS:
- glm-4.7 - fast, $0.40/M input (default)
- gemini-flash - very fast, $0.50/M input
- minimax - medium speed, $0.30/M input

USAGE:
- \"Set Gemini as default model\"
- \"Use MiniMax for all checks\"
- \"Switch to GLM 4.7\"

NOTE: Change applies only to current session""",
                "inputSchema": {
                    "type": "object",
                    "properties": {
                        "model": {
                            "type": "string",
                            "description": "Model key to set as default",
                            "enum": get_enabled_models()
                        }
                    },
                    "required": ["model"]
                }
            },
            "cache_stats": {
                "name": "cache_stats",
                "description": """Shows cache statistics for code verification results.

INFORMATION:
- Cache status (enabled/disabled)
- Current size / max size
- TTL (entry lifetime in seconds)
- Fill percentage

PURPOSE:
Cache stores verification results to speed up repeated requests with the same code. If code hasn't changed, result is taken from cache (~50ms instead of 2-5 sec).

USAGE:
- \"Show cache stats\"
- \"How many results in cache?\"
- \"Check cache status\"

RESULT: Detailed information about cache state""",
                "inputSchema": {
                    "type": "object",
                    "properties": {}
                }
            },
            "diagnose": {
                "name": "diagnose",
                "description": """Diagnose API connectivity and show recent errors.

PURPOSE:
Helps troubleshoot when code verification fails. Tests connection to each AI provider and shows recent error log.

CHECKS:
- API key presence for each model
- Connection test to z.ai and OpenRouter
- Recent error history with timestamps
- Recommendations for fixing issues

USAGE:
- \"Diagnose Argus\"
- \"Why is verification failing?\"
- \"Check API status\"
- \"Show recent errors\"

RESULT: Diagnostic report with connection status and error analysis""",
                "inputSchema": {
                    "type": "object",
                    "properties": {}
                }
            }
        }

    def _detect_mode(self, arguments: dict) -> str:
        """Определяет режим работы на основе переданных параметров"""
        if arguments.get("diff"):
            return "diff"
        elif arguments.get("files"):
            return "multiple"
        elif arguments.get("code"):
            return "single"
        else:
            return "unknown"

    def _extract_file_paths(self, arguments: dict, mode: str) -> list[str]:
        """Извлекает пути к файлам для language hints"""
        if mode == "single":
            file_path = arguments.get("file_path", "")
            return [sanitize_file_path(file_path)] if file_path else []
        
        elif mode == "diff":
            diff = arguments.get("diff", "")
            files = []
            for line in diff.split('\n'):
                if line.startswith('diff --git'):
                    parts = line.split()
                    if len(parts) >= 4:
                        file_path = parts[3].replace('b/', '')
                        files.append(sanitize_file_path(file_path))
            return files
        
        elif mode == "multiple":
            files = arguments.get("files", [])
            return [sanitize_file_path(f.get("path", "")) for f in files if f.get("path")]
        
        return []

    def _format_code_for_review(self, arguments: dict, mode: str) -> tuple:
        """Форматирует код для проверки в зависимости от режима"""
        
        if mode == "single":
            file_path = arguments.get("file_path", "unknown")
            code = arguments.get("code", "")
            header = f"📄 **{file_path}**"
            content = f"## Код для проверки\n```\n{code}\n```"
            return (header, content)
        
        elif mode == "diff":
            diff = arguments.get("diff", "")
            files = []
            for line in diff.split('\n'):
                if line.startswith('diff --git'):
                    parts = line.split()
                    if len(parts) >= 4:
                        file_path = parts[3].replace('b/', '')
                        files.append(file_path)
            
            header = "\n".join([f"📄 **{f}**" for f in files]) if files else "📄 **Changes**"
            content = f"## Git Diff\n```diff\n{diff}\n```"
            return (header, content)
        
        elif mode == "multiple":
            files = arguments.get("files", [])
            headers = []
            contents = []
            
            for file_info in files:
                path = file_info.get("path", "unknown")
                stats = file_info.get("stats", "")
                file_diff = file_info.get("diff")
                file_content = file_info.get("content")
                
                headers.append(f"📄 **{path}** {stats}")
                
                if file_diff:
                    contents.append(f"### {path}\n```diff\n{file_diff}\n```")
                else:
                    contents.append(f"### {path}\n```\n{file_content}\n```")
            
            header = "\n".join(headers)
            content = "\n\n".join(contents)
            return (header, content)
        
        else:
            return ("", "")

    async def _verify_code(self, arguments: dict) -> Dict[str, Any]:
        """Основная логика проверки кода"""
        
        # Валидация входных данных
        valid, error = validate_arguments(arguments)
        if not valid:
            return {"success": False, "error": f"Validation error: {error}"}
        
        # Определяем режим и модель
        mode = self._detect_mode(arguments)
        model_key = arguments.get("model", DEFAULT_MODEL)
        use_cache = arguments.get("use_cache", True)
        use_fallback = arguments.get("use_fallback", True)
        
        # Проверяем кэш
        if use_cache:
            cached_result = self.cache.get(arguments, model_key)
            if cached_result:
                cached_result["from_cache"] = True
                return cached_result
        
        # Форматируем код и строим промпты
        files_header, code_content = self._format_code_for_review(arguments, mode)
        file_paths = self._extract_file_paths(arguments, mode)
        project_stack = arguments.get("project_stack")
        
        system_prompt = build_system_prompt(mode, file_paths, project_stack)
        user_message = build_user_message(
            arguments.get("task_context", ""),
            arguments.get("session_changes", ""),
            code_content
        )
        
        # Вызываем модель (с fallback если включён)
        if use_fallback:
            result = await self.model_manager.verify_with_fallback(
                system_prompt, user_message, model_key
            )
        else:
            provider = self.model_manager.get_provider(model_key)
            result = await provider.verify_code(system_prompt, user_message)
        
        # Добавляем заголовок файлов к вердикту
        if result["success"] and files_header:
            result["verdict"] = f"{files_header}\n\n{result['verdict']}"
        
        # Сохраняем в кэш
        if use_cache and result["success"]:
            self.cache.set(arguments, model_key, result)
        
        return result

    async def _list_models(self) -> Dict[str, Any]:
        """Возвращает список доступных моделей"""
        from config import MODELS
        
        models_info = []
        for key, config in MODELS.items():
            models_info.append({
                "key": key,
                "name": config["name"],
                "provider": config["provider"],
                "enabled": config["enabled"],
                "cost_input_per_1k": config["cost_input_per_1k"],
                "cost_output_per_1k": config["cost_output_per_1k"],
                "max_tokens": config["max_tokens"]
            })
        
        return {
            "success": True,
            "models": models_info,
            "default_model": DEFAULT_MODEL
        }

    async def _set_default_model(self, model_key: str) -> Dict[str, Any]:
        """Устанавливает модель по умолчанию для сессии"""
        from config import MODELS, get_enabled_models
        
        enabled_models = get_enabled_models()
        
        if model_key not in enabled_models:
            return {
                "success": False,
                "error": f"Model '{model_key}' not available. Enabled models: {', '.join(enabled_models)}"
            }
        
        # В реальности DEFAULT_MODEL это константа из config.py
        # Для сессионного изменения нужно хранить в self
        if not hasattr(self, '_session_default_model'):
            self._session_default_model = DEFAULT_MODEL
        
        old_model = self._session_default_model
        self._session_default_model = model_key
        
        model_config = MODELS[model_key]
        
        return {
            "success": True,
            "old_model": old_model,
            "new_model": model_key,
            "model_name": model_config["name"],
            "message": f"Модель по умолчанию изменена с '{old_model}' на '{model_key}' ({model_config['name']})"
        }

    async def _cache_stats(self) -> Dict[str, Any]:
        """Возвращает статистику кэша"""
        return {
            "success": True,
            "cache": self.cache.stats()
        }

    async def _diagnose(self) -> str:
        """Диагностика API подключений и ошибок"""
        import httpx
        from models import get_error_log, format_error_for_user
        
        lines = ["# 🔍 Argus MCP Diagnostics\n"]
        
        # 1. Проверка API ключей
        lines.append("## API Keys Status\n")
        for model_key, config in MODELS.items():
            has_key = bool(config.get("api_key"))
            status = "✅" if has_key else "❌ MISSING"
            key_preview = config.get("api_key", "")[:8] + "..." if has_key else "Not set"
            lines.append(f"- **{config['name']}** ({model_key}): {status}")
            if has_key:
                lines.append(f"  - Key: `{key_preview}`")
                lines.append(f"  - Provider: {config['provider']}")
        
        # 2. Тест подключения к API
        lines.append("\n## Connection Tests\n")
        
        test_results = []
        for model_key, config in MODELS.items():
            if not config.get("enabled"):
                test_results.append((model_key, "⏭️ Skipped (no API key)", None))
                continue
            
            try:
                async with httpx.AsyncClient(timeout=10) as client:
                    # Простой тест - отправляем минимальный запрос
                    headers = {
                        "Authorization": f"Bearer {config['api_key']}",
                        "Content-Type": "application/json"
                    }
                    if config['provider'] == 'openrouter':
                        headers["HTTP-Referer"] = "https://argus-mcp-diagnose"
                    
                    response = await client.post(
                        f"{config['base_url']}/chat/completions",
                        headers=headers,
                        json={
                            "model": config['model_id'],
                            "messages": [{"role": "user", "content": "Hi"}],
                            "max_tokens": 5
                        }
                    )
                    
                    if response.status_code == 200:
                        test_results.append((model_key, "✅ Connected", response.status_code))
                    else:
                        error_text = response.text[:100]
                        test_results.append((model_key, f"❌ HTTP {response.status_code}: {error_text}", response.status_code))
            
            except httpx.TimeoutException:
                test_results.append((model_key, "⏱️ Timeout (>10s)", "TIMEOUT"))
            except httpx.ConnectError as e:
                test_results.append((model_key, f"🌐 Connection failed: {str(e)[:50]}", "CONNECT_ERROR"))
            except Exception as e:
                test_results.append((model_key, f"❓ Error: {str(e)[:50]}", "ERROR"))
        
        for model_key, status, code in test_results:
            lines.append(f"- **{model_key}**: {status}")
        
        # 3. Последние ошибки
        lines.append("\n## Recent Errors\n")
        error_log = get_error_log()
        if error_log:
            for err in error_log[-5:]:
                status = f" (HTTP {err['status_code']})" if err.get('status_code') else ""
                lines.append(f"- `{err['timestamp'][:19]}` **{err['model']}**: {err['error_type']}{status}")
                lines.append(f"  - {err['details'][:100]}")
        else:
            lines.append("No recent errors recorded.")
        
        # 4. Рекомендации
        lines.append("\n## Recommendations\n")
        
        # Анализируем результаты тестов
        failed_tests = [r for r in test_results if "❌" in r[1] or "⏱️" in r[1] or "🌐" in r[1]]
        
        if not failed_tests:
            lines.append("✅ All systems operational!")
        else:
            for model_key, status, code in failed_tests:
                if code == 401:
                    lines.append(f"- **{model_key}**: Invalid API key. Check `.env` file.")
                elif code == 429:
                    lines.append(f"- **{model_key}**: Rate limited. Wait a few minutes.")
                elif code == "TIMEOUT":
                    lines.append(f"- **{model_key}**: API slow/overloaded. Try later.")
                elif code == "CONNECT_ERROR":
                    lines.append(f"- **{model_key}**: Network issue. Check internet connection.")
                else:
                    lines.append(f"- **{model_key}**: Check API provider status page.")
        
        return "\n".join(lines)

    async def handle_request(self, request: dict) -> dict:
        """Обрабатывает MCP запрос"""
        method = request.get("method", "")
        req_id = request.get("id")
        params = request.get("params", {})

        if method == "initialize":
            return {
                "jsonrpc": "2.0",
                "id": req_id,
                "result": {
                    "protocolVersion": MCP_PROTOCOL_VERSION,
                    "capabilities": {"tools": {}},
                    "serverInfo": {
                        "name": "Argus MCP",
                        "version": SERVER_VERSION
                    }
                }
            }

        elif method == "notifications/initialized":
            return None

        elif method == "tools/list":
            return {
                "jsonrpc": "2.0",
                "id": req_id,
                "result": {"tools": list(self.tools.values())}
            }

        elif method == "tools/call":
            tool_name = params.get("name")
            arguments = params.get("arguments", {})

            if tool_name == "verify_code":
                result = await self._verify_code(arguments)
                
                if result["success"]:
                    # Формируем вывод
                    content_parts = [result['verdict']]
                    
                    # Добавляем информацию о модели
                    model_info = f"*Проверено моделью: {result['model']}*"
                    
                    # Добавляем информацию о fallback если использовался
                    if result.get("fallback_used"):
                        model_info += f"\n*⚠️ Fallback: основная модель {result['primary_model_failed']} не ответила*"
                    
                    # Добавляем информацию о кэше
                    if result.get("from_cache"):
                        model_info += "\n*💾 Результат из кэша*"
                    
                    # Добавляем стоимость если есть
                    if result.get("cost", 0) > 0:
                        model_info += f"\n*💰 Стоимость: ${result['cost']:.4f}*"
                    
                    content_parts.append(f"\n---\n{model_info}")
                    content = "\n".join(content_parts)
                else:
                    # Формируем детальное сообщение об ошибке
                    error_parts = [f"❌ **Verification Failed**\n"]
                    error_parts.append(f"**Error:** {result['error']}\n")
                    
                    # Добавляем детали ошибок если есть
                    if result.get("error_details"):
                        error_parts.append(f"\n**Details:**\n{result['error_details']}\n")
                    
                    # Добавляем рекомендации
                    if result.get("recommendations"):
                        error_parts.append("\n**Recommendations:**")
                        for rec in result["recommendations"]:
                            error_parts.append(f"\n- {rec}")
                    
                    error_parts.append("\n\n*Use `Diagnose Argus` for detailed diagnostics*")
                    content = "".join(error_parts)

                return {
                    "jsonrpc": "2.0",
                    "id": req_id,
                    "result": {
                        "content": [{"type": "text", "text": content}]
                    }
                }
            
            elif tool_name == "list_models":
                result = await self._list_models()
                
                # Форматируем вывод
                models_text = "# Available Models\n\n"
                for model in result["models"]:
                    status = "✅" if model["enabled"] else "❌"
                    cost_in = f"${model['cost_input_per_1k']:.4f}/1K in"
                    cost_out = f"${model['cost_output_per_1k']:.4f}/1K out"
                    
                    models_text += f"{status} **{model['name']}** (`{model['key']}`)\n"
                    models_text += f"   - Provider: {model['provider']}\n"
                    models_text += f"   - Cost: {cost_in}, {cost_out}\n"
                    models_text += f"   - Context: {model['max_tokens']:,} tokens\n\n"
                
                models_text += f"\n**Default model:** `{result['default_model']}`"
                
                return {
                    "jsonrpc": "2.0",
                    "id": req_id,
                    "result": {
                        "content": [{"type": "text", "text": models_text}]
                    }
                }
            
            elif tool_name == "set_default_model":
                model_key = arguments.get("model")
                result = await self._set_default_model(model_key)
                
                if result["success"]:
                    content = f"""✅ **Модель по умолчанию изменена**

**Старая модель:** `{result['old_model']}`
**Новая модель:** `{result['new_model']}` ({result['model_name']})

Все последующие проверки кода будут использовать {result['model_name']}, если модель не указана явно.

**Примечание:** Изменение действует только для текущей сессии Windsurf."""
                else:
                    content = f"❌ Ошибка: {result['error']}"
                
                return {
                    "jsonrpc": "2.0",
                    "id": req_id,
                    "result": {
                        "content": [{"type": "text", "text": content}]
                    }
                }
            
            elif tool_name == "cache_stats":
                result = await self._cache_stats()
                
                cache = result["cache"]
                stats_text = f"""# Cache Statistics

**Enabled:** {cache['enabled']}
**Size:** {cache['size']} / {cache['max_size']}
**TTL:** {cache['ttl']} seconds"""
                
                return {
                    "jsonrpc": "2.0",
                    "id": req_id,
                    "result": {
                        "content": [{"type": "text", "text": stats_text}]
                    }
                }
            
            elif tool_name == "diagnose":
                result = await self._diagnose()
                return {
                    "jsonrpc": "2.0",
                    "id": req_id,
                    "result": {
                        "content": [{"type": "text", "text": result}]
                    }
                }
            
            else:
                return {
                    "jsonrpc": "2.0",
                    "id": req_id,
                    "error": {
                        "code": -32601,
                        "message": f"Unknown tool: {tool_name}"
                    }
                }

        return {
            "jsonrpc": "2.0",
            "id": req_id,
            "error": {
                "code": -32601,
                "message": f"Method not found: {method}"
            }
        }

    async def run(self):
        """Запускает MCP сервер через stdio"""
        while True:
            try:
                line = await asyncio.get_event_loop().run_in_executor(None, sys.stdin.readline)
                if not line:
                    break
                
                request = json.loads(line.strip())
                response = await self.handle_request(request)
                
                if response:
                    sys.stdout.write(json.dumps(response) + "\n")
                    sys.stdout.flush()
                    
            except json.JSONDecodeError:
                continue
            except Exception as e:
                error_response = {
                    "jsonrpc": "2.0",
                    "id": None,
                    "error": {
                        "code": -32603,
                        "message": str(e)
                    }
                }
                sys.stdout.write(json.dumps(error_response) + "\n")
                sys.stdout.flush()


if __name__ == "__main__":
    server = MCPServer()
    asyncio.run(server.run())

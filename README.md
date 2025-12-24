# 🔱 Argus MCP

**AI-powered code review MCP server with Zero-Trust approach**

[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](https://opensource.org/licenses/MIT)
[![Python 3.11+](https://img.shields.io/badge/python-3.11+-blue.svg)](https://www.python.org/downloads/)
[![MCP Protocol](https://img.shields.io/badge/MCP-2024--11--05-green.svg)](https://modelcontextprotocol.io)

Argus MCP is a Model Context Protocol (MCP) server that provides rigorous code review through multiple AI models. Named after the all-seeing guardian of Greek mythology, it watches over your code with vigilance.

**Works with any MCP-compatible client:**
- ✅ Windsurf IDE
- ✅ Claude Desktop
- ✅ Other MCP clients

**Multilingual support:**
- 🇷🇺 Russian
- 🇬🇧 English
- 🇨🇳 Chinese
- And more - responds in the language of your request

## ✨ Features

- 🛡️ **Zero-Trust Code Review** - Senior QA Engineer & Security Auditor approach
- 🔄 **Multiple AI Models** - GLM 4.7, Gemini 3 Flash Preview, MiniMax M2.1
- 🚀 **Smart Retry & Fallback** - Exponential backoff with automatic model switching
- 💾 **Intelligent Caching** - 1-hour TTL cache for faster repeated checks
- 🌍 **Language-Aware** - Specialized checks for 10+ programming languages
- 📊 **Three Review Modes** - Single file, Git diff, Multiple files
- 🔒 **Security First** - OWASP checks, performance analysis, architecture review

## 🎯 Review Categories

- **❌ Must Fix** - Critical bugs, security flaws, crashes
- **🟡 Should Fix** - Logic gaps, risky patterns, poor UX
- **🟢 Suggestions** - Code style, optimizations, best practices

## 🔌 Compatibility & Setup

Argus works with any MCP-compatible client.

### 🌊 Windsurf
**File:** `~/.codeium/windsurf/mcp_config.json`

```json
{
  "mcpServers": {
    "argus": {
      "command": "/absolute/path/to/argus-mcp/venv/bin/python",
      "args": ["/absolute/path/to/argus-mcp/server_v2.py"]
    }
  }
}
```

**Reload:** Cmd+Shift+P → "Reload Window"

### 🤖 Claude Desktop (Mac)
**File:** `~/Library/Application Support/Claude/claude_desktop_config.json`

```json
{
  "mcpServers": {
    "argus": {
      "command": "/absolute/path/to/argus-mcp/venv/bin/python",
      "args": ["/absolute/path/to/argus-mcp/server_v2.py"]
    }
  }
}
```

**Reload:** Restart Claude Desktop application

### 🖱️ Cursor
**Setup via UI:**

1. Go to **Cursor Settings** → **Features** → **MCP**
2. Click **+ Add New MCP Server**
3. Fill in the fields:
   - **Name:** `argus`
   - **Type:** `stdio`
   - **Command:** `/absolute/path/to/argus-mcp/venv/bin/python /absolute/path/to/argus-mcp/server_v2.py`

**Reload:** Restart Cursor

### 🔧 Other MCP Clients
Use standard MCP stdio protocol configuration.

**Important:** Replace `/absolute/path/to/argus-mcp` with your actual installation path!

## 🚀 Quick Start

### 1. Installation

```bash
git clone https://github.com/yourusername/argus-mcp.git
cd argus-mcp
python3 -m venv venv
source venv/bin/activate  # On Windows: venv\Scripts\activate
pip install -r requirements.txt
```

### 2. Configuration

Create `.env` file:

```bash
cp .env.example .env
```

Edit `.env` with your API keys:

```env
GLM_API_KEY=your_glm_api_key
OPENROUTER_API_KEY=your_openrouter_api_key
DEFAULT_MODEL=glm-4.7
```

**Get API Keys:**
- GLM 4.7: https://api.z.ai
- OpenRouter: https://openrouter.ai/keys

### 3. Windsurf Setup

Add to `~/.codeium/windsurf/mcp_config.json`:

```json
{
  "mcpServers": {
    "argus": {
      "command": "/path/to/argus-mcp/venv/bin/python",
      "args": ["/path/to/argus-mcp/server_v2.py"],
      "env": {}
    }
  }
}
```

### 4. Reload Your MCP Client

**Windsurf:** Cmd+Shift+P → "Reload Window"

**Claude Desktop:** Restart the application

**Other MCP clients:** Follow their reload instructions

## 🛠️ Available Tools

### 1. verify_code

Performs comprehensive code review with Zero-Trust mindset.

**Modes:**
- **Single File** - Review one file with full context
- **Git Diff** - Review changes only (saves tokens)
- **Multiple Files** - Cross-file dependency analysis

**Usage:**
```
Check my work
Review this code with Gemini
Verify changes in multiple files
```

### 2. list_models

Shows available AI models and their status.

**Usage:**
```
Show available models
What models can I use?
```

### 3. set_default_model

Sets default model for the session.

**Usage:**
```
Set Gemini as default model
Use MiniMax for all checks
```

### 4. cache_stats

Displays cache statistics.

**Usage:**
```
Show cache stats
How many results are cached?
```

## 🤖 Supported Models

| Model | Provider | Cost | Speed | Quality |
|-------|----------|------|-------|---------|
| **GLM 4.7** | z.ai | $0.002/1K | Fast | Excellent |
| **Gemini 3 Flash Preview** | OpenRouter | $0.001/1K | Very Fast | Excellent |
| **MiniMax M2.1** | OpenRouter | $0.001/1K | Medium | Good |

## 🌍 Language Support

Specialized checks for:
- Python (PEP 8, type hints, async/await)
- JavaScript (ESLint, async patterns, null safety)
- TypeScript (strict types, interfaces, generics)
- Vue.js (Composition API, reactivity, props)
- React (Hooks, props typing, event handlers)
- Go (error handling, goroutines, defer)
- Rust (ownership, borrowing, lifetimes)
- Java (SOLID, exceptions, streams)
- PHP (PSR standards, type declarations)

## 📊 Architecture

```
argus-mcp/
├── config.py          # Configuration & API keys
├── validators.py      # Input validation (200KB limit)
├── models.py          # Model providers with retry/fallback
├── prompts.py         # Language-aware prompts
├── cache.py           # Result caching (1h TTL)
├── server_v2.py       # Main MCP server
├── .env               # API keys (gitignored)
├── .env.example       # Template
└── requirements.txt   # Dependencies
```

## 🔒 Security Features

- ✅ API keys in `.env` (not in code)
- ✅ Input validation (200KB code limit)
- ✅ Path sanitization
- ✅ `.gitignore` protection
- ✅ OWASP security checks

## 🧪 Testing

```bash
# Test all modes
python test_v2.py

# Test specific model
python test_gemini.py

# Test set_default_model
python test_set_model.py
```

## 📈 Performance

| Metric | Value |
|--------|-------|
| Response time (cached) | ~50ms |
| Response time (API) | 2-5 sec |
| Success rate (with retry) | 99.9% |
| Token savings (language hints) | 30-50% |

## 🤝 Contributing

Contributions are welcome! Please feel free to submit a Pull Request.

1. Fork the repository
2. Create your feature branch (`git checkout -b feature/AmazingFeature`)
3. Commit your changes (`git commit -m 'Add some AmazingFeature'`)
4. Push to the branch (`git push origin feature/AmazingFeature`)
5. Open a Pull Request

## 📝 License

This project is licensed under the MIT License - see the [LICENSE](LICENSE) file for details.

## 🙏 Credits

- **GLM 4.7** by Z.AI
- **Gemini 3 Flash Preview** by Google (via OpenRouter)
- **MiniMax M2.1** by MiniMax (via OpenRouter)
- **MCP Protocol** by Anthropic

## 📞 Support

- 📖 [Documentation](./README_V2.md)
- 🐛 [Report Bug](https://github.com/yourusername/argus-mcp/issues)
- 💡 [Request Feature](https://github.com/yourusername/argus-mcp/issues)

---

**Made with ❤️ for better code quality**

**Version:** 2.0.0  
**Last Updated:** December 2025

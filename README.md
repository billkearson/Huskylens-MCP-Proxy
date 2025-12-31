# MCP SSE Proxy for Huskylens 2

This is a lightweight proxy server for the Huskylens 2 AI device that filters image content from the Model Context Protocol (MCP) Server-Sent Events (SSE) streams. Designed to work with Huskylens 2 or similar devices that send image data through MCP making the responses compatible with Large Language Models (LLM) like Copilot or Claude. 

The Huskylens 2 MCP server as of firmware version 1.2.1 currently returns image and text data in the get_recognition_result responses with no option to provide text only responses. Copilot or other Large Language Models (LLM) solutions did not handle this well and caused "unsupported format" errors. This MCP proxy was the solution to remove the unwanted data. 

## Features

- **SSE Proxy**: Transparently proxies SSE connections between clients and MCP servers
- **Image Filtering**: Removes `image/png` and other image MIME types from responses
- **LLM Compatibility**: Ensures content is properly formatted for LLM consumption
- **Bidirectional Communication**: Handles both SSE streams and POST message endpoints
- **Configurable**: Command-line arguments for host, port, and logging configuration
- **Graceful Shutdown**: Clean shutdown handling for connections

## Requirements

- Python 3.8+
- aiohttp
- Huskylens 2 with WiFi card
- Host to run this python MCP proxy
- Passion for LLMs and edge AI devices

## Installation

1. Clone or download this repository
2. Install dependencies:

```bash
pip install aiohttp
```

## Usage

### Basic Usage

Run with default settings:

```bash
python MCProxy.py
```

This starts the proxy on `127.0.0.1:3000` and forwards to `192.168.2.186:3000`.

### Command Line Arguments

| Argument | Default | Description |
|----------|---------|-------------|
| `--listen-host` | `127.0.0.1` | Host address to listen on |
| `--listen-port` | `3000` | Port to listen on |
| `--target-host` | `192.168.2.186` | Target MCP server host |
| `--target-port` | `3000` | Target MCP server port |
| `--log-level` | `INFO` | Logging level (DEBUG, INFO, WARNING, ERROR, CRITICAL) |

### Examples

```bash
# Listen on all interfaces
python MCProxy.py --listen-host 0.0.0.0

# Use a different port
python MCProxy.py --listen-port 8080

# Connect to a different target
python MCProxy.py --target-host 192.168.1.100 --target-port 5000

# Enable debug logging
python MCProxy.py --log-level DEBUG

# Full example
python MCProxy.py --listen-host 0.0.0.0 --listen-port 8080 --target-host 192.168.1.100 --target-port 3000 --log-level INFO
```

### Using the Batch File

A convenience batch file is provided:

```bash
MCProxy.bat
```

## Endpoints

| Endpoint | Method | Description |
|----------|--------|-------------|
| `/` | GET | Health check - returns "MCP SSE Proxy is running" |
| `/sse` | GET | SSE proxy endpoint - connects to upstream and filters responses |
| `/message` | POST | Message proxy - forwards JSON-RPC messages to upstream |

## How It Works

1. **Client connects** to the proxy's `/sse` endpoint
2. **Proxy connects** to the upstream MCP server's SSE endpoint
3. **Messages are filtered** as they pass through:
   - Image content (`image/png`, etc.) is removed
   - `resource_link` types are filtered out
   - `mimeType` fields are stripped from remaining content
   - Content is reformatted for API compatibility
4. **Filtered messages** are forwarded to the client

## Configuration for VS Code MCP

Add to your `.vscode/mcp.json`:

```json
{
  "servers": {
    "Huskylens": {
      "url": "http://127.0.0.1:3000/sse"
    }
  }
}
```

## Architecture

```
┌─────────────┐     ┌─────────────┐     ┌─────────────────┐
│   Client    │────▶│  MCP Proxy  │────▶│  Huskylens/MCP  │
│  (VS Code)  │◀────│  (Filter)   │◀────│     Server      │
└─────────────┘     └─────────────┘     └─────────────────┘
                          │
                    Filters out:
                    - image/png
                    - image/*
                    - resource_link
```

## Logging

The proxy logs various events:

- **INFO**: Connection events, filtered messages summary
- **DEBUG**: Full message content, parsing details
- **WARNING**: Non-critical issues
- **ERROR**: Exceptions and failures

Example output:
```
2025-12-31 14:30:00,123 - __main__ - INFO - Starting MCP SSE Proxy on http://127.0.0.1:3000/sse
2025-12-31 14:30:00,124 - __main__ - INFO - Proxying to http://192.168.2.186:3000/sse
2025-12-31 14:30:05,456 - __main__ - INFO - New SSE connection from 127.0.0.1
2025-12-31 14:30:05,789 - __main__ - INFO - Filtered 1 image/png items from content array
```

## License

MIT License



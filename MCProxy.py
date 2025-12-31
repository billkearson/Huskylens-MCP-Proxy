import asyncio
import argparse
import aiohttp
from aiohttp import web
import json
import logging

# Logger will be configured after parsing args
logger = logging.getLogger(__name__)

# Default Configuration
DEFAULT_LISTEN_HOST = '127.0.0.1'
DEFAULT_LISTEN_PORT = 3000
DEFAULT_TARGET_HOST = '192.168.2.186'
DEFAULT_TARGET_PORT = 3000
DEFAULT_LOG_LEVEL = 'INFO'

# These will be set from command line args
LISTEN_HOST = DEFAULT_LISTEN_HOST
LISTEN_PORT = DEFAULT_LISTEN_PORT
TARGET_HOST = DEFAULT_TARGET_HOST
TARGET_PORT = DEFAULT_TARGET_PORT
TARGET_URL = f'http://{TARGET_HOST}:{TARGET_PORT}/sse'


async def filter_sse_message(line: str) -> str:
    """
    Filter SSE messages to remove image/png mimeType content.
    Returns empty string if message should be filtered, otherwise returns the line.
    Ensures content is properly formatted for Claude API.
    """
    logger.debug(f"Filter SSE Message Line: {line}")
    if not line.startswith('data:'):
        return line
    
    try:
        # Extract JSON data from SSE format
        data_content = line[5:].strip()  # Remove 'data:' prefix
        if not data_content:
            logger.debug("Returned line: not data_content:")
            return line
            
        # Parse JSON
        message_data = json.loads(data_content)
        
        # Check if this message contains image mimeType
        if isinstance(message_data, dict):
            # Check for mimeType at top level
            mime_type = message_data.get('mimeType', '')
            if mime_type.startswith('image/'):
                logger.info(f"Filtered message with mimeType: {mime_type}")
                return ''
            
            # Determine where content is located (could be at top level or nested in 'result' for JSON-RPC)
            content = None
            content_parent = None
            if 'content' in message_data:
                content = message_data['content']
                content_parent = message_data
            elif 'result' in message_data and isinstance(message_data['result'], dict) and 'content' in message_data['result']:
                content = message_data['result']['content']
                content_parent = message_data['result']
            
            # Check nested structures (content arrays, etc.)
            if content is not None:
                if isinstance(content, list):
                    # Save and filter out image/png items from content arrays
                    filtered_content = []
                    text_parts = []
                    
                    for item in content:
                        if isinstance(item, dict):
                            mime_type = item.get('mimeType', '')
                            item_type = item.get('type', '')
                            # Filter out any image content or resource_link types
                            if mime_type.startswith('image/') or item_type == 'resource_link':
                                logger.info(f"Filtered item with mimeType: {mime_type} or type: {item_type} from content array")
                            else:
                                # Keep non-image, non-resource_link items
                                # Remove mimeType field even from kept items
                                if 'mimeType' in item:
                                    item = {k: v for k, v in item.items() if k != 'mimeType'}
                                filtered_content.append(item)
                                # If it's a text item, collect the text
                                if item.get('type') == 'text' and 'text' in item:
                                    text_parts.append(item['text'])
                        else:
                            # Keep non-dict items
                            filtered_content.append(item)
                    
                    if len(filtered_content) != len(content):
                        logger.info(f"Filtered {len(content) - len(filtered_content)} image/png items from content array")
                        logger.debug(f"Filtered content: {filtered_content}, text_parts: {text_parts}")
                        
                        if not filtered_content:
                            # If all content was filtered, skip this message
                            logger.info("All content filtered, skipping message")
                            return ''
                        
                        # Convert filtered content to proper Claude API format
                        if filtered_content:
                            # If there's non-text content, convert to proper Claude format
                            # Claude expects: {"type": "text", "text": "..."} for text items
                            proper_content = []
                            for item in filtered_content:
                                if isinstance(item, dict):
                                    if item.get('type') == 'text' and 'text' in item:
                                        proper_content.append(item)
                                    elif 'text' in item:
                                        # Ensure type is set to 'text'
                                        proper_content.append({"type": "text", "text": item['text']})
                                    elif isinstance(item, str):
                                        # Convert string items to proper format
                                        proper_content.append({"type": "text", "text": item})
                                elif isinstance(item, str):
                                    # Convert string items to proper format
                                    proper_content.append({"type": "text", "text": item})
                            
                            if proper_content:
                                content_parent['content'] = proper_content
                                logger.info(f"Converted {len(proper_content)} items to Claude format")
                            else:
                                # If no valid content, skip message
                                logger.info("No valid content after conversion, skipping message")
                                return ''
                        else:
                            # No content left after filtering
                            logger.info("No content remaining after filtering, skipping message")
                            return ''
                        
                        return f"data: {json.dumps(message_data)}\n"
                elif isinstance(content, dict):
                    mime_type = content.get('mimeType', '')
                    if mime_type.startswith('image/'):
                        logger.info(f"Filtered content object with mimeType: {mime_type}")
                        return ''
        
        # Return the (possibly modified) message_data
        logger.debug(f"Filter SSE Message Line, returned line: {json.dumps(message_data)}")
        return f"data: {json.dumps(message_data)}\n"
    except json.JSONDecodeError:
        # Not JSON, pass through as-is
        logger.debug(f"Filter SSE Message Line, json error: {line}")
        return line
    except Exception as e:
        logger.error(f"Error filtering message: {e}", exc_info=True)
        logger.debug(f"Filter SSE Message Line, error: {line}")
        return line

async def proxy_sse(request):
    """
    Proxy SSE requests to target server with filtering.
    Handles bidirectional MCP communication through SSE.
    """
    logger.info(f"New SSE connection from {request.remote}")
    
    response = web.StreamResponse()
    response.headers['Content-Type'] = 'text/event-stream'
    response.headers['Cache-Control'] = 'no-cache'
    response.headers['Connection'] = 'keep-alive'
    await response.prepare(request)
    
    session = None
    try:
        timeout = aiohttp.ClientTimeout(total=None, connect=10, sock_read=60)
        session = aiohttp.ClientSession(timeout=timeout)
        async with session.get(TARGET_URL) as upstream_response:
            logger.info(f"Connected to upstream server: {TARGET_URL}")
            
            buffer = ""
            async for chunk in upstream_response.content.iter_any():
                if chunk:
                    buffer += chunk.decode('utf-8')
                    
                    # Process complete lines
                    while '\n' in buffer:
                        line, buffer = buffer.split('\n', 1)
                        line = line + '\n'
                        
                        # Filter and write directly
                        filtered_line = await filter_sse_message(line)
                        if filtered_line:
                            await response.write(filtered_line.encode('utf-8'))
    except asyncio.CancelledError:
        logger.info("Client disconnected")
    except Exception as e:
        logger.error(f"Proxy error: {e}")
    finally:
        if session and not session.closed:
            await session.close()
        try:
            await response.write_eof()
        except:
            pass
    
    return response

async def proxy_message(request):
    """
    Proxy POST requests to the MCP message endpoint.
    This handles the bidirectional communication - client sends messages via POST.
    """
    # Get the full path including query string
    full_path = request.path_qs
    logger.info(f"Message POST from {request.remote} to {full_path}")
    
    try:
        # Read the request body
        request_body = await request.read()
        
        # Construct the target URL
        target_message_url = f'http://{TARGET_HOST}:{TARGET_PORT}{full_path}'
        
        # Forward the request to upstream
        async with aiohttp.ClientSession() as session:
            async with session.post(
                target_message_url,
                data=request_body,
                headers={'Content-Type': 'application/json'}
            ) as upstream_response:
                response_data = await upstream_response.read()
                
                logger.info(f"Message forwarded to {target_message_url}, status: {upstream_response.status}")
                logger.debug(f"Response data: {response_data.decode('utf-8')}")

                return web.Response(
                    body=response_data,
                    status=upstream_response.status,
                    content_type='application/json'
                )
    
    except Exception as e:
        logger.error(f"Message proxy error: {e}")
        return web.Response(
            text=json.dumps({"error": str(e)}),
            status=500,
            content_type='application/json'
        )

async def health_check(request):
    """Health check endpoint."""
    return web.Response(text="MCP SSE Proxy is running")

async def on_shutdown(app):
    """Graceful shutdown handler."""
    logger.info("Shutting down proxy...")
    # Close any persistent connections

def create_app():
    """Create and configure the application."""
    app = web.Application()
    app.router.add_get('/sse', proxy_sse)
    app.router.add_post('/message', proxy_message)  # Handle MCP message POST requests
    app.router.add_get('/', health_check)
    app.on_shutdown.append(on_shutdown)
    return app

def parse_args():
    """Parse command line arguments."""
    parser = argparse.ArgumentParser(
        description='MCP SSE Proxy - Filters image content from SSE streams'
    )
    parser.add_argument(
        '--listen-host',
        default=DEFAULT_LISTEN_HOST,
        help=f'Host to listen on (default: {DEFAULT_LISTEN_HOST})'
    )
    parser.add_argument(
        '--listen-port',
        type=int,
        default=DEFAULT_LISTEN_PORT,
        help=f'Port to listen on (default: {DEFAULT_LISTEN_PORT})'
    )
    parser.add_argument(
        '--target-host',
        default=DEFAULT_TARGET_HOST,
        help=f'Target host to proxy to (default: {DEFAULT_TARGET_HOST})'
    )
    parser.add_argument(
        '--target-port',
        type=int,
        default=DEFAULT_TARGET_PORT,
        help=f'Target port to proxy to (default: {DEFAULT_TARGET_PORT})'
    )
    parser.add_argument(
        '--log-level',
        default=DEFAULT_LOG_LEVEL,
        choices=['DEBUG', 'INFO', 'WARNING', 'ERROR', 'CRITICAL'],
        help=f'Logging level (default: {DEFAULT_LOG_LEVEL})'
    )
    return parser.parse_args()

if __name__ == '__main__':
    args = parse_args()
    
    # Configure logging based on command line argument
    logging.basicConfig(
        level=getattr(logging, args.log_level),
        format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
    )
    
    # Update global configuration from args
    LISTEN_HOST = args.listen_host
    LISTEN_PORT = args.listen_port
    TARGET_HOST = args.target_host
    TARGET_PORT = args.target_port
    TARGET_URL = f'http://{TARGET_HOST}:{TARGET_PORT}/sse'
    
    logger.info(f"Starting MCP SSE Proxy on http://{LISTEN_HOST}:{LISTEN_PORT}/sse")
    logger.info(f"Proxying to {TARGET_URL}")
    logger.info("Filtering: mimeType='image/png' will be removed")
    
    app = create_app()
    web.run_app(app, host=LISTEN_HOST, port=LISTEN_PORT)

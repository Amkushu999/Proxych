import aiohttp
import asyncio
import time
import socket
import ipaddress
import re
import json
import logging
import sys
import concurrent.futures
from urllib.parse import urlparse
from typing import Dict, List, Tuple, Optional, Union, Any

# Configure logger
logger = logging.getLogger(__name__)

# RapidAPI configuration - updated API key and endpoint
RAPIDAPI_URL = "https://proxy-checker.p.rapidapi.com/api/proxy-checker"
RAPIDAPI_HEADERS = {
    'x-rapidapi-host': 'proxy-checker.p.rapidapi.com',
    'x-rapidapi-key': 'fc738aba33mshe8c764e178fe5e8p129629jsn729ea73984a6',
    'Content-Type': 'application/json',
    'Accept': 'application/json'
}

# Test sites for proxy checking - expanded reliable test endpoints (backup if RapidAPI fails)
TEST_SITES = [
    "http://httpbin.org/get",       # Primary HTTP test
    "https://httpbin.org/get",      # Primary HTTPS test
    "http://example.com",           # Simple and fast HTTP fallback
    "https://example.com",          # Simple and fast HTTPS fallback
    "http://ip-api.com/json",       # Alternative IP service 
    "https://ifconfig.me/all.json", # Alternative IP service (HTTPS)
    "http://ip.jsontest.com"        # Very minimal IP test
]

# Maximum number of concurrent checks - increased for better performance
MAX_CONCURRENT_CHECKS = 20

# Connection timeout settings - increased for better reliability
CONNECT_TIMEOUT = 12  # Increased for better reliability with slower proxies
REQUEST_TIMEOUT = 18  # Increased for better API response rate
SOCKET_TIMEOUT = 8    # Increased for better socket connection reliability

class ProxyChecker:
    """Class to handle proxy checking operations with improved concurrency"""
    
    def __init__(self, max_concurrent: int = MAX_CONCURRENT_CHECKS):
        """
        Initialize the proxy checker with concurrency settings
        
        Args:
            max_concurrent: Maximum number of concurrent proxy checks
        """
        self.max_concurrent = max_concurrent
        self.semaphore = asyncio.Semaphore(max_concurrent)
        self.connector = None
        
    async def initialize(self):
        """Initialize the TCP connector with appropriate limits and optimizations"""
        if self.connector is None or self.connector.closed:
            self.connector = aiohttp.TCPConnector(
                limit=self.max_concurrent,
                limit_per_host=2,  # Reduced to avoid overloading single hosts
                ssl=False,         # Disable SSL verification for faster checks
                ttl_dns_cache=300, # Cache DNS to reduce lookups
                force_close=True,  # Force close connections to prevent hanging
                keepalive_timeout=5.0 # Shorter keepalive for more responsive checks
            )
        
    async def close(self):
        """Close the connector when done"""
        if self.connector and not self.connector.closed:
            await self.connector.close()
            
    async def get_client_session(self) -> aiohttp.ClientSession:
        """Get a client session with the configured connector"""
        await self.initialize()
        return aiohttp.ClientSession(
            connector=self.connector,
            timeout=aiohttp.ClientTimeout(
                total=REQUEST_TIMEOUT,
                connect=CONNECT_TIMEOUT
            )
        )
            
    async def check_proxy(self, proxy_str: str, username: Optional[str] = None) -> str:
        """
        Check if a proxy is alive and gather comprehensive information about it.
        Uses RapidAPI for faster and more reliable results.
        
        Args:
            proxy_str: Proxy in format 'ip:port' or 'ip:port:username:password'
            username: Telegram username of the person who initiated the check
            
        Returns:
            A formatted string with detailed check results
        """
        async with self.semaphore:
            # Parse the proxy string
            proxy_data = self._parse_proxy_string(proxy_str)
            if isinstance(proxy_data, str):
                # Return error message if parsing failed
                return proxy_data
                
            host, port, auth = proxy_data
            
            # Validate IP and port
            validation_result = self._validate_ip_port(host, port)
            if validation_result:
                return validation_result
            
            # Initialize connection time from socket check
            socket_result = await self._check_socket_connection(host, port)
            if socket_result.get('error'):
                return f"❌ Proxy <code>{proxy_str}</code> is not responding. {socket_result['error']}"
            
            connection_time = socket_result.get('time', 0)
            
            # Format proxy for authentication if needed
            auth_str = ""
            if auth:
                auth_str = f"{auth.login}:{auth.password}@"
            
            proxy_data = {
                "host": host,
                "port": port,
                "auth": auth_str
            }
            
            # Try RapidAPI first (faster and more reliable)
            try:
                session = await self.get_client_session()
                async with session:
                    # Use RapidAPI to check the proxy
                    start_time = time.time()
                    
                    params = {
                        "proxyIp": host,
                        "proxyPort": str(port),
                    }
                    
                    # Add auth parameters if available
                    if auth:
                        params["proxyUsername"] = auth.login
                        params["proxyPassword"] = auth.password
                    
                    try:
                        # Convert params to JSON for better RapidAPI compatibility
                        payload = {
                            "proxyIp": host,
                            "proxyPort": port,
                        }
                        
                        # Add auth parameters if available
                        if auth:
                            payload["proxyUsername"] = auth.login
                            payload["proxyPassword"] = auth.password
                            
                        # Use a shorter timeout for RapidAPI to avoid waiting too long
                        api_timeout = aiohttp.ClientTimeout(total=REQUEST_TIMEOUT * 0.8, connect=CONNECT_TIMEOUT)
                        
                        async with session.post(
                            RAPIDAPI_URL,
                            headers=RAPIDAPI_HEADERS,
                            json=payload,
                            timeout=api_timeout,
                            ssl=False  # Disable SSL for faster API calls
                        ) as resp:
                            elapsed = time.time() - start_time
                            
                            # Be more forgiving with RapidAPI response status codes
                            if 200 <= resp.status < 500:
                                try:
                                    # Add safety timeout for JSON parsing
                                    json_task = asyncio.create_task(resp.json())
                                    data = await asyncio.wait_for(json_task, timeout=5.0)
                                    
                                    # Process RapidAPI response with more flexible validation
                                    if data:
                                        # Standard successful response format
                                        if "status" in data and data["status"] == "success":
                                            result_data = data.get("data", {})
                                        # Alternate format sometimes returned
                                        elif "isHttpProxyValid" in data or "isHttpsProxyValid" in data:
                                            result_data = data
                                        
                                        # Extract protocol data from the response
                                        http_result = {
                                            'protocol': 'HTTP',
                                            'working': result_data.get("isHttpProxyValid", False),
                                            'status': '✅ Working' if result_data.get("isHttpProxyValid", False) else '❌ Failed',
                                            'time': elapsed,
                                        }
                                        
                                        https_result = {
                                            'protocol': 'HTTPS',
                                            'working': result_data.get("isHttpsProxyValid", False),
                                            'status': '✅ Working' if result_data.get("isHttpsProxyValid", False) else '❌ Failed',
                                            'time': elapsed,
                                        }
                                        
                                        socks4_result = {
                                            'protocol': 'SOCKS4',
                                            'working': result_data.get("isSocks4ProxyValid", False),
                                            'status': '✅ Working' if result_data.get("isSocks4ProxyValid", False) else '❌ Failed',
                                            'time': elapsed,
                                        }
                                        
                                        socks5_result = {
                                            'protocol': 'SOCKS5',
                                            'working': result_data.get("isSocks5ProxyValid", False),
                                            'status': '✅ Working' if result_data.get("isSocks5ProxyValid", False) else '❌ Failed',
                                            'time': elapsed,
                                        }
                                        
                                        # We got valid results from RapidAPI
                                        return self._format_response(
                                            proxy_str=proxy_str,
                                            connection_time=connection_time,
                                            http_result=http_result,
                                            https_result=https_result,
                                            socks4_result=socks4_result,
                                            socks5_result=socks5_result,
                                            username=username
                                        )
                                except Exception as e:
                                    logger.error(f"Error parsing RapidAPI response: {str(e)}")
                    except Exception as e:
                        logger.error(f"Error using RapidAPI: {str(e)}")
            except Exception as e:
                logger.error(f"Failed to use RapidAPI: {str(e)}")
                
            # Fallback to manual testing if RapidAPI failed
            logger.info("Falling back to manual proxy testing")
            
            # Prepare proxy URLs for different protocols
            proxy_url = f"{host}:{port}"
            http_proxy = f"http://{proxy_url}"
            socks4_proxy = f"socks4://{proxy_url}"
            socks5_proxy = f"socks5://{proxy_url}"
            
            if auth:
                # Add authentication to URLs
                http_proxy = f"http://{auth.login}:{auth.password}@{proxy_url}"
                socks4_proxy = f"socks4://{auth.login}:{auth.password}@{proxy_url}"
                socks5_proxy = f"socks5://{auth.login}:{auth.password}@{proxy_url}"
            
            # Test proxies with different protocols and multiple fallback endpoints
            tasks = [
                self._test_proxy_with_fallbacks(http_proxy, [
                    "http://httpbin.org/get", 
                    "http://ip-api.com/json",
                    "http://example.com"
                ], "HTTP"),
                self._test_proxy_with_fallbacks(http_proxy, [
                    "https://httpbin.org/get", 
                    "https://ifconfig.me/all.json",
                    "https://example.com"
                ], "HTTPS"),
                self._test_proxy_with_fallbacks(socks4_proxy, [
                    "http://httpbin.org/get",
                    "http://ip.jsontest.com",
                    "http://example.com"
                ], "SOCKS4"),
                self._test_proxy_with_fallbacks(socks5_proxy, [
                    "http://httpbin.org/get",
                    "http://ip-api.com/json",
                    "http://example.com"
                ], "SOCKS5")
            ]
            
            results = await asyncio.gather(*tasks)
            http_result, https_result, socks4_result, socks5_result = results
            
            # Build detailed response
            return self._format_response(
                proxy_str=proxy_str,
                connection_time=connection_time,
                http_result=http_result,
                https_result=https_result,
                socks4_result=socks4_result,
                socks5_result=socks5_result,
                username=username
            )

    def _parse_proxy_string(self, proxy_str: str) -> Union[Tuple[str, int, Optional[aiohttp.BasicAuth]], str]:
        """
        Parse a proxy string into components
        
        Args:
            proxy_str: Proxy string in format 'ip:port' or 'ip:port:username:password'
            
        Returns:
            Tuple of (host, port, auth) or error message string
        """
        parts = proxy_str.split(':')
        
        if len(parts) == 2:
            # ip:port format
            host, port_str = parts
            try:
                port = int(port_str)
                return host, port, None
            except ValueError:
                return "Invalid port number. Must be an integer."
        elif len(parts) == 4:
            # ip:port:username:password format
            host, port_str, username, password = parts
            try:
                port = int(port_str)
                auth = aiohttp.BasicAuth(username, password)
                return host, port, auth
            except ValueError:
                return "Invalid port number. Must be an integer."
        else:
            return "Invalid proxy format. Use 'ip:port' or 'ip:port:username:password'"
    
    def _validate_ip_port(self, host: str, port: int) -> Optional[str]:
        """
        Validate IP address and port
        
        Args:
            host: IP address to validate
            port: Port number to validate
            
        Returns:
            Error message if validation fails, None if valid
        """
        # Accept all IPs/hostnames without strict validation for better compatibility
        if port < 1 or port > 65535:
            return "Invalid port number. Port must be between 1 and 65535."
        return None
            
    def _is_valid_hostname(self, hostname: str) -> bool:
        """
        Check if a string is a valid hostname
        
        Args:
            hostname: Hostname to validate
            
        Returns:
            True if valid hostname, False otherwise
        """
        if len(hostname) > 255:
            return False
        if hostname.endswith('.'):
            hostname = hostname[:-1]
        allowed = re.compile(r"(?!-)[A-Z\d-]{1,63}(?<!-)$", re.IGNORECASE)
        return all(allowed.match(x) for x in hostname.split("."))
    
    async def _check_socket_connection(self, host: str, port: int) -> Dict[str, Any]:
        """
        Check basic socket connection to the proxy
        
        Args:
            host: Host IP or hostname
            port: Port number
            
        Returns:
            Dictionary with connection result and time or error
        """
        result = {'connected': False, 'time': 0.0}
        
        # Use ThreadPoolExecutor for blocking socket operations
        with concurrent.futures.ThreadPoolExecutor() as executor:
            try:
                loop = asyncio.get_event_loop()
                connection_start = time.time()
                
                # Run socket connection in thread pool
                future = loop.run_in_executor(
                    executor,
                    self._socket_connect,
                    host,
                    port
                )
                
                connection_result = await future
                connection_time = time.time() - connection_start
                
                result['time'] = connection_time
                if connection_result != 0:
                    result['error'] = f"Connection error (code: {connection_result})"
                else:
                    result['connected'] = True
                    
            except Exception as e:
                result['error'] = f"Error: {str(e)}"
                
        return result
    
    def _socket_connect(self, host: str, port: int) -> int:
        """
        Perform actual socket connection (blocking operation)
        
        Args:
            host: Host to connect to
            port: Port to connect to
            
        Returns:
            Socket connection result code (0 means success)
        """
        # Try both IPv4 and IPv6 if needed
        for socket_family in [socket.AF_INET, socket.AF_INET6]:
            try:
                sock = socket.socket(socket_family, socket.SOCK_STREAM)
                sock.settimeout(SOCKET_TIMEOUT)
                result = sock.connect_ex((host, port))
                sock.close()
                
                if result == 0:
                    # If connection succeeded, return success immediately
                    return 0
                    
            except (socket.gaierror, socket.error, OSError):
                # Skip this address family and try the next
                continue
                
        # If we reach here, both IPv4 and IPv6 have failed or been skipped
        # Retry once more with standard IPv4
        sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        sock.settimeout(SOCKET_TIMEOUT)
        try:
            result = sock.connect_ex((host, port))
            return result
        except:
            return 111  # Connection refused
        finally:
            sock.close()
    
    async def _test_proxy_with_fallbacks(self,
                                 proxy: str,
                                 test_urls: List[str],
                                 protocol: str) -> Dict[str, Any]:
        """
        Test a proxy against multiple fallback URLs to reduce false negatives
        
        Args:
            proxy: Proxy URL (e.g., 'http://1.2.3.4:8080')
            test_urls: List of URLs to try in order until one works
            protocol: Protocol being tested (for reporting)
            
        Returns:
            A dictionary with detailed test results
        """
        # Initialize result with a default failed state
        default_result = {
            'protocol': protocol,
            'working': False,
            'status': f'❌ Not working with {protocol}',
            'time': 0.0,
        }
        
        last_result = default_result
        
        # Create tasks for all URLs at once to run them in parallel
        tasks = [self._test_proxy(proxy, url, protocol) for url in test_urls]
        
        try:
            # Wait for all tasks with a timeout
            results = await asyncio.wait_for(
                asyncio.gather(*tasks, return_exceptions=True),
                timeout=REQUEST_TIMEOUT * 1.5
            )
            
            # Process results
            for i, result in enumerate(results):
                if isinstance(result, Exception):
                    # Skip exceptions, but log them
                    logger.debug(f"Error testing {protocol} with {test_urls[i]}: {str(result)}")
                    continue
                    
                # Track this as the last valid result
                last_result = result
                
                # If any test works, immediately return success
                if result.get('working', False):
                    logger.debug(f"Proxy {proxy} working with {protocol} on {test_urls[i]}")
                    return result
            
        except asyncio.TimeoutError:
            # Timeout waiting for all tests
            logger.debug(f"Timeout testing {protocol} proxy {proxy}")
            
            # Try to cancel any pending tasks
            for task in tasks:
                if not task.done():
                    task.cancel()
        
        # If we get here, none of the URLs worked, return the last valid result or default
        return last_result

    async def _test_proxy(self, 
                          proxy: str, 
                          test_url: str, 
                          protocol: str) -> Dict[str, Any]:
        """
        Test a proxy by making a request to a test URL - optimized for reliability
        
        Args:
            proxy: Proxy URL (e.g., 'http://1.2.3.4:8080')
            test_url: URL to test the proxy with
            protocol: Protocol being tested (for reporting)
            
        Returns:
            A dictionary with detailed test results
        """
        result = {
            'protocol': protocol,
            'working': False,
            'status': '❌ Failed',
            'time': 0.0,
        }
        
        # Use a shorter timeout for the entire operation
        try:
            # Create a client session with the proxy
            session = await self.get_client_session()
            
            # Use an even shorter timeout for the actual request
            timeout = aiohttp.ClientTimeout(total=REQUEST_TIMEOUT * 0.8)
            
            async with session:
                # Configure the proxy
                start_time = time.time()
                try:
                    # Simplified headers to reduce overhead
                    headers = {
                        'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) Chrome/112.0.0.0 Safari/537.36',
                        'Accept': '*/*',
                        'Connection': 'close',  # Use close to prevent connection pooling issues
                    }
                    
                    # Create a task with timeout
                    request_task = asyncio.create_task(
                        session.get(
                            test_url,
                            proxy=proxy,
                            headers=headers,
                            allow_redirects=True,
                            timeout=timeout,
                            ssl=False  # Disable SSL for faster checks
                        )
                    )
                    
                    # Add a safety timeout
                    try:
                        response = await asyncio.wait_for(request_task, timeout=REQUEST_TIMEOUT)
                        
                        async with response:
                            elapsed = time.time() - start_time
                            result['time'] = elapsed
                            
                            # More lenient status code check: Accept any non-server-error status code
                            # Status codes: 200-299 (success), 300-399 (redirect), 400-499 (client error)
                            # All these indicate the proxy is working, just the target might have issues
                            if response.status < 500:
                                result['working'] = True
                                result['status'] = f'✅ Working ({elapsed:.2f}s)'
                                
                                # Additional checks based on content
                                content_type = response.headers.get('Content-Type', '')
                                
                                # Try to parse the response for details
                                if 'application/json' in content_type:
                                    try:
                                        # Use a timeout for reading the response body
                                        read_task = asyncio.create_task(response.json())
                                        response_json = await asyncio.wait_for(read_task, timeout=2.0)
                                        
                                        # Extract IP if available
                                        if 'origin' in response_json:
                                            result['ip'] = response_json['origin'].split(',')[0].strip()
                                        elif 'query' in response_json:
                                            result['ip'] = response_json['query']
                                        
                                        # Determine anonymity level
                                        headers = response_json.get('headers', {})
                                        forwarded_for = headers.get('X-Forwarded-For', '')
                                        real_ip = headers.get('X-Real-Ip', '')
                                        via = headers.get('Via', '')
                                        
                                        if not forwarded_for and not real_ip and not via:
                                            result['anonymity'] = 'Elite (Level 1)'
                                        elif not forwarded_for and (real_ip or via):
                                            result['anonymity'] = 'Anonymous (Level 2)'
                                        else:
                                            result['anonymity'] = 'Transparent (Level 3)'
                                            
                                    except asyncio.TimeoutError:
                                        logger.debug(f"Response reading timeout for {protocol}")
                                    except Exception as e:
                                        logger.debug(f"JSON parsing error: {str(e)}")
                                else:
                                    # For non-JSON responses, just mark as working without reading the body
                                    result['working'] = True
                            else:
                                result['status'] = f"❌ HTTP {response.status}"
                                
                    except asyncio.TimeoutError:
                        result['status'] = "❌ Request Timeout"
                        # Try to cancel the task if it's still running
                        if not request_task.done():
                            request_task.cancel()
                            
                except asyncio.TimeoutError:
                    result['status'] = "❌ Timeout"
                except aiohttp.ClientProxyConnectionError:
                    result['status'] = "❌ Proxy Connection Error"
                except aiohttp.ClientConnectorError:
                    result['status'] = "❌ Connection Failed"
                except aiohttp.ClientSSLError:
                    result['status'] = "❌ SSL Error"
                except aiohttp.ClientError:
                    result['status'] = "❌ Client Error"
                except asyncio.CancelledError:
                    result['status'] = "❌ Request Cancelled"
                except Exception as e:
                    result['status'] = f"❌ Error: {type(e).__name__}"
                    logger.debug(f"Error testing {protocol} proxy: {str(e)}")
                    
        except Exception as e:
            result['status'] = f"❌ Error: {type(e).__name__}"
            logger.debug(f"Error in _test_proxy for {protocol}: {str(e)}")
        
        return result
    
    async def _get_geolocation(self, ip: str) -> Dict[str, Any]:
        """
        Get geolocation data for an IP address
        
        Args:
            ip: IP address to look up
            
        Returns:
            Dictionary with geolocation data
        """
        geo_data = {}
        
        try:
            # Create a client session without proxy for geolocation queries
            session = await self.get_client_session()
            async with session:
                # Try ip-api.com for geolocation data
                async with session.get(
                    f"http://ip-api.com/json/{ip}",
                    timeout=aiohttp.ClientTimeout(total=5),
                ) as response:
                    if response.status == 200:
                        data = await response.json()
                        if data.get('status') == 'success':
                            geo_data = {
                                'country': data.get('country', 'Unknown'),
                                'country_code': data.get('countryCode', ''),
                                'region': data.get('regionName', ''),
                                'city': data.get('city', ''),
                                'isp': data.get('isp', ''),
                                'org': data.get('org', ''),
                                'as': data.get('as', ''),
                                'latitude': data.get('lat', 0),
                                'longitude': data.get('lon', 0),
                                'timezone': data.get('timezone', ''),
                            }
        except Exception as e:
            logger.debug(f"Geolocation error: {str(e)}")
        
        return geo_data
    
    def _format_response(self, 
                         proxy_str: str,
                         connection_time: float,
                         http_result: Dict[str, Any],
                         https_result: Dict[str, Any],
                         socks4_result: Dict[str, Any],
                         socks5_result: Dict[str, Any],
                         username: Optional[str] = None) -> str:
        """
        Format the proxy check results into a readable message
        
        Args:
            proxy_str: Original proxy string
            connection_time: Basic connection time in seconds
            http_result: HTTP proxy test results
            https_result: HTTPS proxy test results
            socks4_result: SOCKS4 proxy test results
            socks5_result: SOCKS5 proxy test results
            geo_data: Geographic location data
            username: Telegram username of the person who initiated the check
            
        Returns:
            Formatted response message
        """
        # Build response
        response = [
            f"🔍 <b>Proxy Check Results:</b>",
            f"<code>{proxy_str}</code>",
            f"",
            f"⏱ Connection time: {connection_time:.3f} seconds",
            f"",
        ]
        
        # Protocol results - only show details if working
        protocol_results = [
            (http_result, "🌐 HTTP"),
            (https_result, "🔒 HTTPS"),
            (socks4_result, "🧦 SOCKS4"),
            (socks5_result, "🧦 SOCKS5")
        ]
        
        working_protocols = []
        
        for result, prefix in protocol_results:
            response.append(f"{prefix}: {result['status']}")
            
            if result['working']:
                working_protocols.append(result['protocol'])
                if result.get('anonymity'):
                    response.append(f"  ↳ Anonymity: {result['anonymity']}")
                if result.get('ip'):
                    response.append(f"  ↳ Detected IP: {result['ip']}")
                    
            # Add spacing after each protocol section
            response.append("")
        
        # Geolocation functionality has been removed as requested
        # No additional location information displayed
        
        # Overall status - show working even if just one protocol works
        if working_protocols:
            working_str = ", ".join(working_protocols)
            response.insert(0, f"✅ Proxy <b>{proxy_str}</b> is working! ({working_str})")
        else:
            response.insert(0, f"❌ Proxy <b>{proxy_str}</b> is not working with any protocols")
        
        # Add signature
        response.append("")
        response.append("──────────────────")
        if username:
            response.append(f"Checked by: @{username}")
        response.append(f"Powered by 𝗣𝗿𝗼𝘅𝘆𝗖𝗛𝗞")
        
        return "\n".join(response)

# Create a global instance
proxy_checker = ProxyChecker()

async def check_proxy(proxy_str: str, username: Optional[str] = None) -> str:
    """
    Main function to check a proxy
    
    Args:
        proxy_str: Proxy string to check
        username: Username of the person requesting the check
        
    Returns:
        Formatted check results
    """
    try:
        return await proxy_checker.check_proxy(proxy_str, username)
    except Exception as e:
        logger.error(f"Error checking proxy: {str(e)}")
        return f"❌ An error occurred while checking the proxy: {str(e)}"

async def check_multiple_proxies(proxy_list: List[str], username: Optional[str] = None) -> List[str]:
    """
    Check multiple proxies concurrently with improved reliability and timeout handling
    
    Args:
        proxy_list: List of proxy strings to check
        username: Username of the person requesting the check
        
    Returns:
        List of check results
    """
    try:
        # Initialize the proxy checker first
        await proxy_checker.initialize()
        
        # Create individual tasks for each proxy check
        tasks = []
        for proxy in proxy_list:
            # Create the task
            task = asyncio.create_task(check_proxy(proxy, username))
            # Set a name for better debugging
            task.set_name(f"check_{proxy}")
            tasks.append(task)
        
        # Process tasks in batches to avoid overwhelming the system
        batch_size = min(10, len(proxy_list))
        results = []
        
        # Process in batches with a maximum timeout
        for i in range(0, len(tasks), batch_size):
            batch = tasks[i:i+batch_size]
            try:
                # Wait for the batch with a maximum timeout
                batch_results = await asyncio.wait_for(
                    asyncio.gather(*batch, return_exceptions=True),
                    timeout=REQUEST_TIMEOUT * 3  # Longer timeout for batch processing
                )
                
                # Process results - convert exceptions to error messages
                for j, result in enumerate(batch_results):
                    if isinstance(result, Exception):
                        proxy_idx = i + j
                        proxy = proxy_list[proxy_idx] if proxy_idx < len(proxy_list) else "unknown"
                        error_msg = f"❌ Error checking proxy {proxy}: {str(result)}"
                        logger.error(error_msg)
                        results.append(error_msg)
                    else:
                        results.append(result)
                        
            except asyncio.TimeoutError:
                # Timeout for the entire batch
                for j in range(len(batch)):
                    proxy_idx = i + j
                    proxy = proxy_list[proxy_idx] if proxy_idx < len(proxy_list) else "unknown"
                    results.append(f"❌ Timeout checking proxy {proxy}")
                
                # Try to cancel any remaining tasks in this batch
                for task in batch:
                    if not task.done():
                        task.cancel()
        
        return results
    except Exception as e:
        logger.error(f"Error in check_multiple_proxies: {str(e)}")
        return [f"❌ An error occurred in batch processing: {str(e)}"]
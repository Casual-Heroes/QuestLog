"""
RSS feed security utilities — SSRF-protected fetch and URL validation.

Shared between app.views (bot dashboard RSS) and app.questlog_web (QuestLog RSS feeds).
"""

# Feed fetch limits
RSS_FETCH_TIMEOUT = 30        # seconds
RSS_MAX_SIZE = 5 * 1024 * 1024  # 5 MB
RSS_MAX_REDIRECTS = 5


def validate_rss_url(url):
    """
    Validate RSS feed URL for security with comprehensive SSRF protections.

    Blocks:
    - Non-HTTP(S) schemes
    - Localhost/loopback addresses (IPv4 and IPv6)
    - Internal/private IP ranges (all resolved addresses)
    - Link-local, reserved, and multicast addresses
    - .local and internal domain patterns

    Returns:
        tuple: (is_valid: bool, error_message: str or None)
    """
    from urllib.parse import urlparse
    import ipaddress
    import socket

    if not url:
        return False, 'URL is required'

    url = url.strip()

    if len(url) > 500:
        return False, 'URL too long (max 500 characters)'

    try:
        parsed = urlparse(url)
    except Exception:
        return False, 'Invalid URL format'

    if parsed.scheme not in ('http', 'https'):
        return False, 'URL must use HTTP or HTTPS'

    if not parsed.netloc:
        return False, 'Invalid URL - no host specified'

    hostname = parsed.hostname
    if not hostname:
        return False, 'Invalid URL - no hostname'

    hostname_lower = hostname.lower()

    blocked_hosts = {
        'localhost', '127.0.0.1', '::1', '0.0.0.0',
        '[::1]', '[::ffff:127.0.0.1]', '[0:0:0:0:0:0:0:1]',
        '0', '0.0', '0.0.0', '127.1', '127.0.1'
    }
    if hostname_lower in blocked_hosts:
        return False, 'Localhost URLs are not allowed'

    blocked_suffixes = ['.local', '.internal', '.private', '.corp', '.lan', '.intranet', '.localdomain']
    for suffix in blocked_suffixes:
        if hostname_lower.endswith(suffix):
            return False, f'Internal domains ({suffix}) are not allowed'

    metadata_hosts = ['169.254.169.254', 'metadata.google.internal', 'metadata.goog']
    if hostname_lower in metadata_hosts:
        return False, 'Cloud metadata endpoints are not allowed'

    try:
        addr_info = socket.getaddrinfo(hostname, None, socket.AF_UNSPEC, socket.SOCK_STREAM)

        if not addr_info:
            return False, 'Could not resolve hostname'

        for family, sock_type, proto, canonname, sockaddr in addr_info:
            ip_str = sockaddr[0]

            try:
                ip_obj = ipaddress.ip_address(ip_str)

                if ip_obj.is_private:
                    return False, f'Private IP address not allowed: {ip_str}'
                if ip_obj.is_loopback:
                    return False, f'Loopback address not allowed: {ip_str}'
                if ip_obj.is_link_local:
                    return False, f'Link-local address not allowed: {ip_str}'
                if ip_obj.is_reserved:
                    return False, f'Reserved address not allowed: {ip_str}'
                if ip_obj.is_multicast:
                    return False, f'Multicast address not allowed: {ip_str}'

                if isinstance(ip_obj, ipaddress.IPv6Address) and ip_obj.ipv4_mapped:
                    mapped_v4 = ip_obj.ipv4_mapped
                    if mapped_v4.is_private or mapped_v4.is_loopback or mapped_v4.is_link_local:
                        return False, f'IPv4-mapped address not allowed: {ip_str}'

            except ValueError:
                continue

    except socket.gaierror:
        pass
    except Exception:
        pass

    return True, None


def secure_fetch_rss(url, timeout=RSS_FETCH_TIMEOUT, max_size=RSS_MAX_SIZE):
    """
    Securely fetch and parse an RSS feed with SSRF protections.

    - Validates URL before fetching
    - Validates each redirect hop
    - Enforces timeout and size limits
    - Fetches content first, then parses (prevents feedparser from following redirects)

    Returns:
        tuple: (parsed_feed or None, error_message or None)
    """
    import requests
    import feedparser

    is_valid, error = validate_rss_url(url)
    if not is_valid:
        return None, error

    try:
        current_url = url
        redirect_count = 0

        while redirect_count <= RSS_MAX_REDIRECTS:
            response = requests.get(
                current_url,
                timeout=timeout,
                stream=True,
                allow_redirects=False,
                headers={
                    'User-Agent': 'QuestLog RSS Bot/1.0',
                    'Accept': 'application/rss+xml, application/xml, application/atom+xml, text/xml, */*'
                }
            )

            if response.is_redirect or response.status_code in (301, 302, 303, 307, 308):
                redirect_url = response.headers.get('Location')
                if not redirect_url:
                    return None, 'Redirect with no Location header'

                if redirect_url.startswith('/'):
                    from urllib.parse import urlparse, urlunparse
                    parsed = urlparse(current_url)
                    redirect_url = urlunparse((parsed.scheme, parsed.netloc, redirect_url, '', '', ''))

                is_valid, error = validate_rss_url(redirect_url)
                if not is_valid:
                    return None, f'Blocked redirect to: {error}'

                current_url = redirect_url
                redirect_count += 1
                response.close()
                continue

            break
        else:
            return None, f'Too many redirects (max {RSS_MAX_REDIRECTS})'

        if response.status_code != 200:
            response.close()
            return None, f'HTTP error: {response.status_code}'

        content_length = response.headers.get('Content-Length')
        if content_length and int(content_length) > max_size:
            response.close()
            return None, f'Feed too large (max {max_size // 1024 // 1024}MB)'

        content = b''
        for chunk in response.iter_content(chunk_size=8192):
            content += chunk
            if len(content) > max_size:
                response.close()
                return None, f'Feed too large (max {max_size // 1024 // 1024}MB)'

        response.close()

        parsed = feedparser.parse(content)

        if parsed.bozo and not parsed.entries:
            bozo_exception = str(parsed.get('bozo_exception', 'Unknown parse error'))
            return None, f'Failed to parse feed: {bozo_exception}'

        return parsed, None

    except requests.Timeout:
        return None, f'Request timed out after {timeout} seconds'
    except requests.ConnectionError as e:
        return None, f'Connection error: {str(e)}'
    except requests.RequestException as e:
        return None, f'Request failed: {str(e)}'
    except Exception as e:
        return None, f'Unexpected error: {str(e)}'

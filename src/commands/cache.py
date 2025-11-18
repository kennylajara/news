"""
Cache management commands.
"""

import click
from db.cache import CacheDatabase


@click.group()
def cache():
    """Manage URL cache."""
    pass


@cache.command()
@click.option('--domain', '-d', default=None, help='Filter by domain')
def stats(domain):
    """
    Show cache statistics.

    Example:
        news cache stats
        news cache stats --domain diariolibre.com
    """
    cache_db = CacheDatabase()

    if domain:
        click.echo(f"Cache statistics for domain: {click.style(domain, bold=True)}\n")
        stats_data = cache_db.get_stats(domain=domain)
    else:
        click.echo(f"Cache statistics (all domains)\n")
        stats_data = cache_db.get_stats()

    if stats_data['total_entries'] == 0:
        click.echo(click.style("No entries in cache", fg="yellow"))
        return

    # Format size
    size_bytes = stats_data['total_size_bytes']
    if size_bytes < 1024:
        size_str = f"{size_bytes} B"
    elif size_bytes < 1024 * 1024:
        size_str = f"{size_bytes / 1024:.2f} KB"
    else:
        size_str = f"{size_bytes / (1024 * 1024):.2f} MB"

    click.echo(f"Total entries: {click.style(str(stats_data['total_entries']), fg='green')}")
    click.echo(f"Total size: {click.style(size_str, fg='green')}")

    if stats_data['oldest_entry']:
        click.echo(f"Oldest entry: {stats_data['oldest_entry'].strftime('%Y-%m-%d %H:%M')}")
    if stats_data['newest_entry']:
        click.echo(f"Newest entry: {stats_data['newest_entry'].strftime('%Y-%m-%d %H:%M')}")

    if not domain and stats_data['domains']:
        click.echo(f"\nDomains in cache: {len(stats_data['domains'])}")
        click.echo("  Use 'news cache domains' for details")


@cache.command()
def domains():
    """
    List all cached domains with statistics.

    Example:
        news cache domains
    """
    cache_db = CacheDatabase()
    domains = cache_db.get_domains()

    if not domains:
        click.echo(click.style("No domains in cache", fg="yellow"))
        return

    click.echo(f"Cached domains ({len(domains)} total):\n")

    # Sort by count descending
    domains.sort(key=lambda x: x['count'], reverse=True)

    output_lines = []
    for d in domains:
        # Format size
        size_bytes = d['total_size']
        if size_bytes < 1024:
            size_str = f"{size_bytes} B"
        elif size_bytes < 1024 * 1024:
            size_str = f"{size_bytes / 1024:.2f} KB"
        else:
            size_str = f"{size_bytes / (1024 * 1024):.2f} MB"

        output_lines.append(
            f"  {click.style(d['domain'], fg='cyan', bold=True)}\n"
            f"    Entries: {d['count']}  |  Size: {size_str}"
        )

    # Use pager if more than 20 domains
    if len(output_lines) > 20:
        click.echo_via_pager('\n'.join(output_lines))
    else:
        click.echo('\n'.join(output_lines))


@cache.command()
@click.option('--domain', '-d', default=None, help='Filter by domain')
@click.option('--limit', '-l', type=int, default=20, help='Number of URLs to show (default: 20)')
@click.option('--no-pager', is_flag=True, help='Disable pager for output')
def list(domain, limit, no_pager):
    """
    List cached URLs.

    Example:
        news cache list
        news cache list --domain diariolibre.com
        news cache list --limit 50
    """
    cache_db = CacheDatabase()
    entries = cache_db.list_entries(domain=domain, limit=limit)

    if not entries:
        if domain:
            click.echo(click.style(f"No cached URLs for domain '{domain}'", fg="yellow"))
        else:
            click.echo(click.style("No URLs in cache", fg="yellow"))
        return

    output_lines = []
    if domain:
        output_lines.append(f"Cached URLs for {click.style(domain, bold=True)} ({len(entries)} shown):\n")
    else:
        output_lines.append(f"Cached URLs ({len(entries)} shown):\n")

    for i, entry in enumerate(entries, 1):
        # Format size
        size_bytes = entry['content_length']
        if size_bytes < 1024:
            size_str = f"{size_bytes} B"
        elif size_bytes < 1024 * 1024:
            size_str = f"{size_bytes / 1024:.1f} KB"
        else:
            size_str = f"{size_bytes / (1024 * 1024):.1f} MB"

        # Format dates
        created = entry['created_at'].strftime('%Y-%m-%d %H:%M')

        # Truncate hash for display (first 16 chars is enough for uniqueness)
        hash_short = entry['url_hash'][:16]

        # Color status code (green for 2xx, yellow for 3xx, red for 4xx/5xx)
        status = entry['status_code']
        if 200 <= status < 300:
            status_str = click.style(str(status), fg='green')
        elif 300 <= status < 400:
            status_str = click.style(str(status), fg='yellow')
        else:
            status_str = click.style(str(status), fg='red')

        output_lines.append(
            f"{click.style(f'[{i}]', fg='cyan')} {entry['url']}\n"
            f"    Hash: {hash_short}...  |  Status: {status_str}  |  Domain: {entry['domain']}  |  Size: {size_str}  |  Cached: {created}"
        )

    output_text = '\n'.join(output_lines)

    # Use pager if more than 20 entries and not disabled
    if len(entries) > 20 and not no_pager:
        click.echo_via_pager(output_text)
    else:
        click.echo(output_text)


@cache.command()
@click.argument('url_or_hash')
def show(url_or_hash):
    """
    Show details for a cached URL.

    You can provide either the full URL or the URL hash.

    Example:
        news cache show "https://example.com/article"
        news cache show abc123def456...
    """
    cache_db = CacheDatabase()

    # Try to get by URL first, then by hash
    cached = cache_db.get_cached_content(url_or_hash)

    if not cached:
        # Try as hash
        cached = cache_db.get_by_hash(url_or_hash)

    if not cached:
        click.echo(click.style(f"✗ URL not found in cache", fg="red"))
        return

    # Format size
    size_bytes = cached['content_length']
    if size_bytes < 1024:
        size_str = f"{size_bytes} B"
    elif size_bytes < 1024 * 1024:
        size_str = f"{size_bytes / 1024:.2f} KB"
    else:
        size_str = f"{size_bytes / (1024 * 1024):.2f} MB"

    click.echo(f"\n{click.style('Cached URL Details', bold=True)}\n")
    click.echo(f"URL: {cached['url']}")
    click.echo(f"Domain: {cached['domain']}")
    click.echo(f"Hash: {cached.get('url_hash', 'N/A')}")
    click.echo(f"Status Code: {cached['status_code']}")
    click.echo(f"Content Size: {size_str}")
    click.echo(f"Cached At: {cached['created_at'].strftime('%Y-%m-%d %H:%M:%S')}")
    click.echo(f"Last Accessed: {cached['accessed_at'].strftime('%Y-%m-%d %H:%M:%S')}")
    click.echo(f"\nContent preview (first 500 chars):")
    click.echo("-" * 60)
    click.echo(cached['content'][:500] + "..." if len(cached['content']) > 500 else cached['content'])
    click.echo("-" * 60)


@cache.command()
@click.option('--domain', '-d', default=None, help='Only clear cache for this domain')
@click.option('--article', '-a', default=None, help='Delete specific article by URL or hash')
@click.option('--yes', '-y', is_flag=True, help='Skip confirmation prompt')
def clear(domain, article, yes):
    """
    Clear cache entries.

    By default, clears ALL cache. Use --domain to clear only specific domain,
    or --article to delete a specific URL.

    Example:
        news cache clear
        news cache clear --domain diariolibre.com
        news cache clear --article "https://example.com/article"
        news cache clear --article abc123def456
        news cache clear --yes  # Skip confirmation
    """
    cache_db = CacheDatabase()

    # Can't use both --domain and --article
    if domain and article:
        click.echo(click.style("✗ Cannot use --domain and --article together", fg="red"))
        return

    # Delete specific article
    if article:
        # Get the entry first to show what we're deleting
        cached = cache_db.get_cached_content(article)
        if not cached:
            cached = cache_db.get_by_hash(article)

        if not cached:
            click.echo(click.style(f"✗ Article not found in cache", fg="red"))
            return

        # Show what will be deleted and confirm
        click.echo(f"\nAbout to delete:")
        click.echo(f"  URL: {cached['url']}")
        click.echo(f"  Domain: {cached['domain']}")
        click.echo(f"  Hash: {cached['url_hash'][:16]}...")

        if not yes and not click.confirm('\nAre you sure you want to delete this cached article?'):
            click.echo(click.style("Cancelled", fg="yellow"))
            return

        if cache_db.delete_by_url_or_hash(article):
            click.echo(click.style(f"✓ Deleted cached article", fg="green"))
        else:
            click.echo(click.style(f"✗ Failed to delete article", fg="red"))
        return

    # Clear by domain or all
    if not yes and not click.confirm('Are you sure you want to clear the cache?'):
        click.echo(click.style("Cancelled", fg="yellow"))
        return

    if domain:
        count = cache_db.clear_cache(domain=domain)
        if count > 0:
            click.echo(click.style(f"✓ Cleared {count} entries for domain '{domain}'", fg="green"))
        else:
            click.echo(click.style(f"No entries found for domain '{domain}'", fg="yellow"))
    else:
        count = cache_db.clear_cache()
        if count > 0:
            click.echo(click.style(f"✓ Cleared {count} entries from cache", fg="green"))
        else:
            click.echo(click.style("Cache was already empty", fg="yellow"))

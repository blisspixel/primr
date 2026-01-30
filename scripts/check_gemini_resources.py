#!/usr/bin/env python3
"""
Gemini Resource Inspector

Lists all Gemini resources that could be incurring ongoing costs:
- Explicit Context Caches ($1-4.50/M tokens/hour storage)
- File Search Stores (may have storage costs)

Usage:
    python scripts/check_gemini_resources.py
    python scripts/check_gemini_resources.py --delete-caches
    python scripts/check_gemini_resources.py --delete-stores
    python scripts/check_gemini_resources.py --delete-stores --force-empty  # Delete docs first
    python scripts/check_gemini_resources.py --delete-all
"""

import argparse
import os
import sys
from datetime import datetime

# Fix Windows console encoding for Unicode characters
if sys.platform == 'win32':
    sys.stdout.reconfigure(encoding='utf-8', errors='replace')

# Add src to path for imports
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', 'src'))

try:
    from google import genai
except ImportError:
    print("ERROR: google-genai not installed. Run: pip install google-genai")
    sys.exit(1)

try:
    from dotenv import load_dotenv
    load_dotenv()
except ImportError:
    pass  # dotenv optional


def get_api_key():
    """Get Gemini API key from environment."""
    key = os.environ.get('GEMINI_API_KEY')
    if not key:
        print("ERROR: GEMINI_API_KEY not set in environment or .env file")
        sys.exit(1)
    return key


def list_caches(client):
    """List all explicit context caches."""
    print("\n" + "=" * 60)
    print("EXPLICIT CONTEXT CACHES")
    print("(These cost $1-4.50/M tokens/hour just sitting there!)")
    print("=" * 60)
    
    try:
        caches = list(client.caches.list())
        if not caches:
            print("\n✓ No explicit caches found. You're not being charged for cache storage.")
            return []
        
        print(f"\n⚠ Found {len(caches)} cache(s):\n")
        for cache in caches:
            print(f"  Name: {cache.name}")
            if hasattr(cache, 'display_name'):
                print(f"  Display Name: {cache.display_name}")
            if hasattr(cache, 'create_time'):
                print(f"  Created: {cache.create_time}")
            if hasattr(cache, 'expire_time'):
                print(f"  Expires: {cache.expire_time}")
            if hasattr(cache, 'usage_metadata'):
                meta = cache.usage_metadata
                if hasattr(meta, 'total_token_count'):
                    tokens = meta.total_token_count
                    hourly_cost = (tokens / 1_000_000) * 1.00  # Flash rate
                    daily_cost = hourly_cost * 24
                    print(f"  Tokens: {tokens:,}")
                    print(f"  Est. Cost: ${hourly_cost:.4f}/hour (${daily_cost:.2f}/day)")
            print()
        return caches
    except Exception as e:
        print(f"\n⚠ Could not list caches: {e}")
        return []


def list_file_search_stores(client):
    """List all file search stores."""
    print("\n" + "=" * 60)
    print("FILE SEARCH STORES")
    print("(Used by Deep Research for context)")
    print("=" * 60)
    
    try:
        stores = list(client.file_search_stores.list())
        if not stores:
            print("\n✓ No file search stores found.")
            return []
        
        print(f"\n⚠ Found {len(stores)} store(s):\n")
        for store in stores:
            print(f"  Name: {store.name}")
            if hasattr(store, 'display_name'):
                print(f"  Display Name: {store.display_name}")
            if hasattr(store, 'create_time'):
                print(f"  Created: {store.create_time}")
            print()
        return stores
    except Exception as e:
        print(f"\n⚠ Could not list file search stores: {e}")
        return []


def delete_caches(client, caches):
    """Delete all explicit caches."""
    if not caches:
        print("\nNo caches to delete.")
        return
    
    print(f"\nDeleting {len(caches)} cache(s)...")
    for cache in caches:
        try:
            client.caches.delete(name=cache.name)
            print(f"  ✓ Deleted: {cache.name}")
        except Exception as e:
            print(f"  ✗ Failed to delete {cache.name}: {e}")


def delete_documents_in_store(client, store_name, force=True):
    """Delete all documents inside a file search store.
    
    Args:
        client: Gemini client
        store_name: Name of the store
        force: If True, also delete chunks inside documents
    """
    deleted_count = 0
    try:
        # List all documents in the store
        docs = list(client.file_search_stores.documents.list(parent=store_name))
        if not docs:
            return 0
        
        for doc in docs:
            try:
                # Try with config dict for force parameter (REST API style)
                if force:
                    try:
                        client.file_search_stores.documents.delete(
                            name=doc.name,
                            config={"force": True}
                        )
                        deleted_count += 1
                        continue
                    except TypeError:
                        # If config doesn't work, try without force
                        pass
                
                # Fallback: try without force
                client.file_search_stores.documents.delete(name=doc.name)
                deleted_count += 1
            except Exception as e:
                error_str = str(e).lower()
                if 'failed_precondition' in error_str or 'non-empty' in error_str:
                    print(f"    ⚠ Doc {doc.name.split('/')[-1]}: has chunks, cannot delete")
                else:
                    print(f"    ⚠ Could not delete doc: {e}")
        
        return deleted_count
    except Exception as e:
        # API might not support listing documents for all store types
        return -1  # Signal that we couldn't list docs


def delete_stores(client, stores, force_empty=False):
    """Delete all file search stores.
    
    Args:
        client: Gemini client
        stores: List of stores to delete
        force_empty: If True, delete all documents inside stores first
    """
    if not stores:
        print("\nNo stores to delete.")
        return
    
    print(f"\nDeleting {len(stores)} store(s)...")
    if force_empty:
        print("(Force mode: deleting documents inside stores first)\n")
    
    for store in stores:
        store_name = store.name
        
        # If force mode, try to empty the store first
        if force_empty:
            doc_count = delete_documents_in_store(client, store_name)
            if doc_count > 0:
                print(f"  Deleted {doc_count} document(s) from {store_name}")
            elif doc_count == -1:
                print(f"  Could not list documents in {store_name}")
        
        # Now try to delete the store
        try:
            client.file_search_stores.delete(name=store_name)
            print(f"  ✓ Deleted: {store_name}")
        except Exception as e:
            error_str = str(e).lower()
            if 'failed_precondition' in error_str or 'non-empty' in error_str:
                print(f"  ⚠ {store_name}: Non-empty, will be cleaned by retention policy")
            else:
                print(f"  ✗ Failed to delete {store_name}: {e}")


def main():
    parser = argparse.ArgumentParser(
        description="Inspect and clean up Gemini resources that may be incurring costs"
    )
    parser.add_argument(
        '--delete-caches', 
        action='store_true',
        help='Delete all explicit context caches'
    )
    parser.add_argument(
        '--delete-stores',
        action='store_true', 
        help='Delete all file search stores'
    )
    parser.add_argument(
        '--force-empty',
        action='store_true',
        help='Delete documents inside stores before deleting stores (use with --delete-stores)'
    )
    parser.add_argument(
        '--delete-all',
        action='store_true',
        help='Delete all caches and stores'
    )
    args = parser.parse_args()
    
    print("Gemini Resource Inspector")
    print(f"Time: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    
    api_key = get_api_key()
    client = genai.Client(api_key=api_key)
    
    # List resources
    caches = list_caches(client)
    stores = list_file_search_stores(client)
    
    # Delete if requested
    if args.delete_all or args.delete_caches:
        delete_caches(client, caches)
    
    if args.delete_all or args.delete_stores:
        delete_stores(client, stores, force_empty=args.force_empty)
    
    # Summary
    print("\n" + "=" * 60)
    print("SUMMARY")
    print("=" * 60)
    
    if not caches and not stores:
        print("\n✓ No Gemini resources found that could be causing ongoing costs.")
        print("  If you're seeing charges, check:")
        print("  - Google Cloud Console for other projects")
        print("  - Other applications using this API key")
        print("  - AI Studio experiments with caching enabled")
    else:
        if caches:
            print(f"\n⚠ {len(caches)} explicit cache(s) found - these cost money!")
            if not (args.delete_all or args.delete_caches):
                print("  Run with --delete-caches to remove them")
        if stores:
            print(f"\n⚠ {len(stores)} file search store(s) found")
            if not (args.delete_all or args.delete_stores):
                print("  Run with --delete-stores to remove them")


if __name__ == "__main__":
    main()

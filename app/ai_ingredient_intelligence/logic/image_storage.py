"""
Image Storage Utility
====================

Downloads product images from URLs and stores them in S3 for reliable access.
This ensures images are available even if the original URLs become unavailable.
"""

import os
import hashlib
import requests
from typing import Optional
import boto3
from botocore.exceptions import ClientError, NoCredentialsError
from app.ai_ingredient_intelligence.config import AWS_S3_REGION

# S3 Configuration for product images
AWS_S3_BUCKET_PRODUCT_IMAGES = os.getenv("AWS_S3_BUCKET_PRODUCT_IMAGES", os.getenv("AWS_S3_BUCKET_PLATFORM_LOGOS", "skinbb-main"))
AWS_S3_PRODUCT_IMAGES_PREFIX = os.getenv("AWS_S3_PRODUCT_IMAGES_PREFIX", "product_images")

# Try to import PIL for image processing
try:
    from PIL import Image
    import io
    PIL_AVAILABLE = True
except ImportError:
    PIL_AVAILABLE = False
    print("Warning: PIL/Pillow not available. Images will be stored in original format.")


def get_s3_client():
    """Get boto3 S3 client for product images."""
    try:
        client = boto3.client('s3', region_name=AWS_S3_REGION)
        return client
    except NoCredentialsError:
        print("Warning: AWS credentials not found. Image uploads will be skipped.")
        return None
    except Exception as e:
        print(f"Warning: Failed to initialize S3 client: {str(e)}")
        return None


def _generate_image_key(image_url: str) -> str:
    """
    Generate a unique S3 key for an image based on its URL.
    
    Args:
        image_url: Original image URL
        
    Returns:
        S3 key (path) for the image
    """
    # Create a hash of the URL to ensure uniqueness
    url_hash = hashlib.md5(image_url.encode('utf-8')).hexdigest()
    
    # Extract file extension from URL (default to jpg)
    ext = 'jpg'
    if '.' in image_url:
        url_lower = image_url.lower()
        if url_lower.endswith('.png'):
            ext = 'png'
        elif url_lower.endswith('.webp'):
            ext = 'webp'
        elif url_lower.endswith('.gif'):
            ext = 'gif'
        elif url_lower.endswith('.jpeg') or url_lower.endswith('.jpg'):
            ext = 'jpg'
    
    # Use first 8 chars of hash + full hash for uniqueness
    key = f"{AWS_S3_PRODUCT_IMAGES_PREFIX}/{url_hash[:8]}/{url_hash}.{ext}"
    return key


def _check_image_exists_in_s3(image_url: str, s3_client) -> Optional[str]:
    """
    Check if image already exists in S3 based on URL hash.
    
    Args:
        image_url: Original image URL
        s3_client: boto3 S3 client
        
    Returns:
        S3 URL if exists, None otherwise
    """
    if not s3_client:
        return None
    
    try:
        key = _generate_image_key(image_url)
        s3_client.head_object(Bucket=AWS_S3_BUCKET_PRODUCT_IMAGES, Key=key)
        
        # Construct S3 URL
        try:
            region = s3_client.meta.region_name
        except:
            region = AWS_S3_REGION
        url = f"https://{AWS_S3_BUCKET_PRODUCT_IMAGES}.s3.{region}.amazonaws.com/{key}"
        return url
    except ClientError as e:
        error_code = e.response.get('Error', {}).get('Code', 'Unknown')
        if error_code in ('404', 'NoSuchKey'):
            return None
        else:
            print(f"Warning: Error checking image in S3: {error_code}")
            return None
    except Exception as e:
        print(f"Warning: Unexpected error checking image in S3: {str(e)}")
        return None


def _download_image(image_url: str) -> Optional[bytes]:
    """
    Download image from URL.
    
    Args:
        image_url: Image URL to download
        
    Returns:
        Image bytes or None if download fails
    """
    if not image_url or not isinstance(image_url, str):
        return None
    
    # Skip emoji "images"
    if image_url.startswith(('🧴', '✨', '🔍', '🧪', '⚖️', '🚀')):
        return None
    
    # Skip if not a valid URL
    if not image_url.startswith(('http://', 'https://')):
        return None
    
    try:
        headers = {
            'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36'
        }
        response = requests.get(image_url, timeout=15, headers=headers, stream=True)
        response.raise_for_status()
        
        # Verify it's actually an image
        content_type = response.headers.get('Content-Type', '').lower()
        if 'image' not in content_type:
            print(f"Warning: URL did not return an image (Content-Type: {content_type}): {image_url[:100]}")
            return None
        
        # Limit image size to 10MB
        max_size = 10 * 1024 * 1024  # 10MB
        content_length = response.headers.get('Content-Length')
        if content_length and int(content_length) > max_size:
            print(f"Warning: Image too large ({content_length} bytes), skipping: {image_url[:100]}")
            return None
        
        # Read image data
        image_bytes = response.content
        if len(image_bytes) > max_size:
            print(f"Warning: Downloaded image too large ({len(image_bytes)} bytes), skipping: {image_url[:100]}")
            return None
        
        return image_bytes
    except requests.exceptions.RequestException as e:
        print(f"Warning: Failed to download image from {image_url[:100]}: {str(e)}")
        return None
    except Exception as e:
        print(f"Warning: Unexpected error downloading image from {image_url[:100]}: {str(e)}")
        return None


def _convert_to_jpg(image_bytes: bytes) -> Optional[bytes]:
    """
    Convert image to JPG format for consistent storage.
    
    Args:
        image_bytes: Image bytes in any format
        
    Returns:
        JPG image bytes or None
    """
    if not PIL_AVAILABLE:
        # If PIL not available, return original bytes
        return image_bytes
    
    try:
        img = Image.open(io.BytesIO(image_bytes))
        
        # Convert to RGB if necessary (for formats with transparency)
        if img.mode in ('RGBA', 'LA', 'P'):
            background = Image.new('RGB', img.size, (255, 255, 255))
            if img.mode == 'RGBA':
                background.paste(img, mask=img.split()[-1])
            else:
                background.paste(img)
            img = background
        elif img.mode != 'RGB':
            img = img.convert('RGB')
        
        # Convert to JPG
        output = io.BytesIO()
        img.save(output, format='JPEG', quality=85, optimize=True)
        return output.getvalue()
    except Exception as e:
        print(f"Warning: Failed to convert image to JPG: {str(e)}")
        # Return original bytes as fallback
        return image_bytes


async def download_and_store_image(image_url: str) -> Optional[str]:
    """
    Download image from URL and store in S3.
    
    This function:
    1. Checks if image already exists in S3 (by URL hash)
    2. Downloads image if not cached
    3. Converts to JPG format
    4. Uploads to S3
    5. Returns S3 URL
    
    Args:
        image_url: Original image URL
        
    Returns:
        S3 URL of stored image, or original URL if storage fails
    """
    # Validate input
    if not image_url or not isinstance(image_url, str):
        return None
    
    # Skip emoji "images"
    if image_url.startswith(('🧴', '✨', '🔍', '🧪', '⚖️', '🚀')):
        return image_url  # Return emoji as-is
    
    # Skip if not a valid URL
    if not image_url.startswith(('http://', 'https://')):
        return image_url  # Return original if not a URL
    
    # Skip if already an S3 URL (already stored)
    if '.s3.' in image_url and 'amazonaws.com' in image_url:
        print(f"✅ Image is already an S3 URL, skipping storage: {image_url[:100]}")
        return image_url
    
    # Get S3 client
    s3_client = get_s3_client()
    if not s3_client:
        print(f"Warning: S3 client not available, skipping image storage for: {image_url[:100]}")
        return image_url  # Return original URL if S3 not available
    
    # Check if image already exists in S3 (check both original format and JPG)
    existing_url = _check_image_exists_in_s3(image_url, s3_client)
    if existing_url:
        print(f"✅ Image already stored in S3: {existing_url}")
        return existing_url
    
    # Also check for JPG version if we're going to convert
    if PIL_AVAILABLE:
        # Generate JPG key and check if it exists
        url_hash = hashlib.md5(image_url.encode('utf-8')).hexdigest()
        jpg_key = f"{AWS_S3_PRODUCT_IMAGES_PREFIX}/{url_hash[:8]}/{url_hash}.jpg"
        try:
            s3_client.head_object(Bucket=AWS_S3_BUCKET_PRODUCT_IMAGES, Key=jpg_key)
            try:
                region = s3_client.meta.region_name
            except:
                region = AWS_S3_REGION
            jpg_url = f"https://{AWS_S3_BUCKET_PRODUCT_IMAGES}.s3.{region}.amazonaws.com/{jpg_key}"
            print(f"✅ JPG version already stored in S3: {jpg_url}")
            return jpg_url
        except ClientError:
            pass  # JPG version doesn't exist, continue with download
    
    # Download image
    print(f"📥 Downloading image from: {image_url[:100]}")
    image_bytes = _download_image(image_url)
    if not image_bytes:
        print(f"⚠️ Failed to download image, using original URL: {image_url[:100]}")
        return image_url  # Return original URL if download fails
    
    # Convert to JPG
    if PIL_AVAILABLE:
        jpg_bytes = _convert_to_jpg(image_bytes)
        if not jpg_bytes:
            print(f"⚠️ Failed to convert image, using original URL: {image_url[:100]}")
            return image_url
        image_bytes = jpg_bytes
        content_type = 'image/jpeg'
        ext = 'jpg'
    else:
        # Determine content type from original
        content_type = 'image/jpeg'  # Default
        ext = 'jpg'
    
    # Generate S3 key - always use .jpg extension when converting to JPG
    if PIL_AVAILABLE and ext == 'jpg':
        # Generate key with .jpg extension since we're converting
        url_hash = hashlib.md5(image_url.encode('utf-8')).hexdigest()
        key = f"{AWS_S3_PRODUCT_IMAGES_PREFIX}/{url_hash[:8]}/{url_hash}.jpg"
    else:
        # Use original extension if not converting
        key = _generate_image_key(image_url)
    
    # Upload to S3
    try:
        try:
            region = s3_client.meta.region_name
        except:
            region = AWS_S3_REGION
        
        upload_params = {
            'Bucket': AWS_S3_BUCKET_PRODUCT_IMAGES,
            'Key': key,
            'Body': image_bytes,
            'ContentType': content_type
        }
        
        # Try to set ACL, but catch error if bucket ACLs are disabled
        try:
            s3_client.put_object(**upload_params, ACL='public-read')
        except ClientError as acl_error:
            error_code = acl_error.response.get('Error', {}).get('Code', 'Unknown')
            if error_code in ('AccessControlListNotSupported', 'InvalidRequest'):
                s3_client.put_object(**upload_params)
            else:
                raise
        
        # Construct S3 URL
        s3_url = f"https://{AWS_S3_BUCKET_PRODUCT_IMAGES}.s3.{region}.amazonaws.com/{key}"
        print(f"✅ Successfully stored image in S3: {s3_url}")
        return s3_url
        
    except ClientError as e:
        error_code = e.response.get('Error', {}).get('Code', 'Unknown')
        error_msg = e.response.get('Error', {}).get('Message', str(e))
        print(f"⚠️ Failed to upload image to S3 ({error_code}): {error_msg}")
        print(f"   Using original URL: {image_url[:100]}")
        return image_url  # Return original URL if upload fails
    except Exception as e:
        print(f"⚠️ Unexpected error uploading image to S3: {str(e)}")
        print(f"   Using original URL: {image_url[:100]}")
        return image_url  # Return original URL if upload fails


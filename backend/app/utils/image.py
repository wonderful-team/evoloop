"""
Image Processing Utilities

Provides functions for image manipulation, format conversion, and Base64 encoding.
Uses optional Pillow (PIL) for advanced operations when available.
"""

import base64
import io
import os
from typing import BinaryIO

# Optional PIL import
try:
    from PIL import Image
    HAS_PIL = True
except ImportError:
    HAS_PIL = False


def image_to_base64(image_path: str | BinaryIO, format: str | None = None) -> str:
    """
    Convert an image file to Base64 encoded string.
    
    Args:
        image_path: Path to image file, or file-like object
        format: Optional image format (e.g., 'jpeg', 'png'). Auto-detected if not specified.
    
    Returns:
        Base64 encoded string
    
    Raises:
        FileNotFoundError: If image file doesn't exist
        ValueError: If format cannot be determined
    """
    if isinstance(image_path, str):
        with open(image_path, 'rb') as f:
            data = f.read()
    else:
        data = image_path.read()
    
    return base64.b64encode(data).decode('utf-8')


def base64_to_image(base64_str: str, output_path: str) -> None:
    """
    Save a Base64 encoded image to file.
    
    Args:
        base64_str: Base64 encoded image data
        output_path: Path to save the image
    """
    # Remove data URL prefix if present
    if ',' in base64_str:
        base64_str = base64_str.split(',', 1)[1]
    
    data = base64.b64decode(base64_str)
    
    # Ensure output directory exists
    os.makedirs(os.path.dirname(os.path.abspath(output_path)), exist_ok=True)
    
    with open(output_path, 'wb') as f:
        f.write(data)


def get_image_mime_type(image_path: str) -> str:
    """
    Get MIME type for an image file based on extension.
    
    Args:
        image_path: Path to image file
    
    Returns:
        MIME type string (e.g., 'image/jpeg', 'image/png')
    """
    ext = os.path.splitext(image_path)[1].lower()
    
    mime_types = {
        '.jpg': 'image/jpeg',
        '.jpeg': 'image/jpeg',
        '.png': 'image/png',
        '.gif': 'image/gif',
        '.bmp': 'image/bmp',
        '.tiff': 'image/tiff',
        '.tif': 'image/tiff',
        '.webp': 'image/webp',
        '.svg': 'image/svg+xml',
        '.ico': 'image/x-icon',
    }
    
    return mime_types.get(ext, 'application/octet-stream')


def get_image_extension(mime_type: str) -> str:
    """
    Get file extension from MIME type.
    
    Args:
        mime_type: MIME type string (e.g., 'image/jpeg')
    
    Returns:
        File extension with dot (e.g., '.jpg')
    """
    extensions = {
        'image/jpeg': '.jpg',
        'image/png': '.png',
        'image/gif': '.gif',
        'image/bmp': '.bmp',
        'image/tiff': '.tiff',
        'image/webp': '.webp',
        'image/svg+xml': '.svg',
        'image/x-icon': '.ico',
    }
    
    return extensions.get(mime_type, '')


def image_to_data_url(image_path: str) -> str:
    """
    Convert an image to a data URL (data:image/jpeg;base64,...).
    
    Args:
        image_path: Path to image file
    
    Returns:
        Data URL string
    """
    mime_type = get_image_mime_type(image_path)
    base64_data = image_to_base64(image_path)
    return f"data:{mime_type};base64,{base64_data}"


def resize_image(
    image_path: str,
    max_size: tuple[int, int],
    output_path: str | None = None
) -> bytes:
    """
    Resize an image to fit within max_size while maintaining aspect ratio.
    
    Args:
        image_path: Path to image file
        max_size: Maximum (width, height) tuple
        output_path: Optional path to save resized image
    
    Returns:
        Resized image as bytes
    
    Raises:
        ImportError: If Pillow is not installed
    """
    if not HAS_PIL:
        raise ImportError("Pillow is required for image resizing")
    
    with Image.open(image_path) as img:
        # Convert to RGB if necessary (handles RGBA, P, etc.)
        if img.mode in ('RGBA', 'LA', 'P'):
            background = Image.new('RGB', img.size, (255, 255, 255))
            if img.mode == 'P':
                img = img.convert('RGBA')
            if img.mode in ('RGBA', 'LA'):
                background.paste(img, mask=img.split()[-1] if img.mode in ('RGBA', 'LA') else None)
                img = background
        
        # Resize maintaining aspect ratio
        img.thumbnail(max_size, Image.Resampling.LANCZOS)
        
        # Save to bytes
        output = io.BytesIO()
        format = Image.open(image_path).format or 'JPEG'
        img.save(output, format=format)
        data = output.getvalue()
        
        # Optionally save to file
        if output_path:
            os.makedirs(os.path.dirname(os.path.abspath(output_path)), exist_ok=True)
            with open(output_path, 'wb') as f:
                f.write(data)
        
        return data


def get_image_dimensions(image_path: str) -> tuple[int, int]:
    """
    Get image dimensions (width, height).
    
    Args:
        image_path: Path to image file
    
    Returns:
        (width, height) tuple
    
    Raises:
        ImportError: If Pillow is not installed
    """
    if not HAS_PIL:
        raise ImportError("Pillow is required for getting image dimensions")
    
    with Image.open(image_path) as img:
        return img.size


def convert_image_format(
    image_path: str,
    target_format: str,
    output_path: str | None = None,
    quality: int = 95
) -> bytes:
    """
    Convert image to a different format.
    
    Args:
        image_path: Path to source image
        target_format: Target format (e.g., 'JPEG', 'PNG', 'WEBP')
        output_path: Optional path to save converted image
        quality: Quality for lossy formats (1-100)
    
    Returns:
        Converted image as bytes
    
    Raises:
        ImportError: If Pillow is not installed
    """
    if not HAS_PIL:
        raise ImportError("Pillow is required for image format conversion")
    
    with Image.open(image_path) as img:
        # Convert mode if necessary
        if target_format.upper() in ('JPEG', 'JPG') and img.mode in ('RGBA', 'LA', 'P'):
            background = Image.new('RGB', img.size, (255, 255, 255))
            if img.mode == 'P':
                img = img.convert('RGBA')
            if img.mode in ('RGBA', 'LA'):
                background.paste(img, mask=img.split()[-1])
                img = background
        
        output = io.BytesIO()
        save_kwargs = {}
        if target_format.upper() in ('JPEG', 'JPG', 'WEBP'):
            save_kwargs['quality'] = quality
            save_kwargs['optimize'] = True
        
        img.save(output, format=target_format, **save_kwargs)
        data = output.getvalue()
        
        if output_path:
            os.makedirs(os.path.dirname(os.path.abspath(output_path)), exist_ok=True)
            with open(output_path, 'wb') as f:
                f.write(data)
        
        return data


def create_thumbnail(
    image_path: str,
    size: tuple[int, int] = (128, 128),
    output_path: str | None = None
) -> bytes:
    """
    Create a thumbnail of an image.
    
    Args:
        image_path: Path to image file
        size: Thumbnail size (width, height)
        output_path: Optional path to save thumbnail
    
    Returns:
        Thumbnail image as bytes
    """
    return resize_image(image_path, size, output_path)


def is_valid_image(image_path: str) -> bool:
    """
    Check if file is a valid image.
    
    Args:
        image_path: Path to file
    
    Returns:
        True if file is a valid image
    """
    if not os.path.exists(image_path):
        return False
    
    if HAS_PIL:
        try:
            with Image.open(image_path) as img:
                img.verify()
            return True
        except (OSError, TypeError, ValueError):
            return False
    else:
        # Basic check using extension
        ext = os.path.splitext(image_path)[1].lower()
        return ext in {'.jpg', '.jpeg', '.png', '.gif', '.bmp', '.tiff', '.webp'}

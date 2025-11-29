#!/usr/bin/env python3
"""
Phone number utilities for consistent handling
"""


def normalize_phone(phone: str) -> str:
    """
    Normalize phone number for storage
    Ensures it starts with + and has no spaces

    Args:
        phone: Phone number in any format

    Returns:
        Normalized phone (e.g., +79213885903)
    """
    # Remove all spaces
    phone = phone.strip().replace(' ', '').replace('-', '')

    # Add + if missing
    if not phone.startswith('+'):
        phone = '+' + phone

    return phone


def phone_to_filename(phone: str) -> str:
    """
    Convert phone number to session filename (without +)

    Args:
        phone: Phone number (with or without +)

    Returns:
        Filename-safe phone (e.g., 79213885903)
    """
    # Remove + and spaces
    return phone.replace('+', '').replace(' ', '').replace('-', '')


def filename_to_phone(filename: str) -> str:
    """
    Convert session filename back to phone number (with +)

    Args:
        filename: Session filename without extension

    Returns:
        Phone number with + (e.g., +79213885903)
    """
    # Remove extension if present
    filename = filename.replace('.session', '')

    # Add + if it doesn't start with it
    if not filename.startswith('+'):
        return '+' + filename

    return filename

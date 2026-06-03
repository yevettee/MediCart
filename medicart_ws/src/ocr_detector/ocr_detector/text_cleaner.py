"""Text post-processing for OCR output."""


def clean_text(raw_text):
    """Remove newlines and normalize whitespace."""
    return ' '.join(raw_text.split())

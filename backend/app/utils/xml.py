"""
XML Processing Utilities

Provides safe XML parsing and content extraction functions.
"""

import logging
import re
from xml.etree import ElementTree as ET

logger = logging.getLogger(__name__)


def clean_xml_content(xml_content: str) -> str:
    """
    Clean XML content by removing invalid characters and extracting valid XML section.

    This handles common issues with XML from Android UI dumps and other sources,
    including control characters, incomplete XML, and wrapper text.

    Args:
        xml_content: Raw XML content that may contain invalid characters

    Returns:
        Cleaned XML string ready for parsing

    Examples:
        >>> clean_xml_content("prefix<?xml version='1.0'?>\\n<root/>\\nsuffix")
        "<?xml version='1.0'?>\\n<root/>"
        >>> clean_xml_content("<hierarchy>\\x00\\x01text</hierarchy>")
        "<hierarchy>text</hierarchy>"
    """
    if not xml_content or not isinstance(xml_content, str):
        return ""

    xml_content = xml_content.strip()

    # Find XML declaration or root element
    xml_start = xml_content.find("<?xml")
    if xml_start == -1:
        xml_start = xml_content.find("<")

    if xml_start > 0:
        xml_content = xml_content[xml_start:]

    # Find the end of the root element
    # Handle self-closing tags and nested elements
    hierarchy_end = xml_content.rfind("</hierarchy>")
    if hierarchy_end != -1:
        xml_content = xml_content[: hierarchy_end + len("</hierarchy>")]
    else:
        # For other root elements, try to find the last closing tag
        last_close = xml_content.rfind(">")
        if last_close != -1 and "/>" not in xml_content[last_close-1:last_close+1]:
            # Find the corresponding closing tag
            first_tag_match = re.search(r"<(\w+)[\s>]", xml_content)
            if first_tag_match:
                root_tag = first_tag_match.group(1)
                close_tag = f"</{root_tag}>"
                close_pos = xml_content.rfind(close_tag)
                if close_pos != -1:
                    xml_content = xml_content[: close_pos + len(close_tag)]

    # Remove invalid XML control characters
    # XML 1.0 valid: #x9 | #xA | #xD | [#x20-#xD7FF] | [#xE000-#xFFFD] | [#x10000-#x10FFFF]
    xml_content = re.sub(r"[\x00-\x08\x0b\x0c\x0e-\x1f\x7f-\x9f]", "", xml_content)

    return xml_content


def safe_parse_xml(xml_content: str) -> ET.Element | None:
    """
    Safely parse XML content with automatic cleaning.

    Args:
        xml_content: Raw XML content

    Returns:
        Parsed ElementTree Element, or None if parsing fails
    """
    cleaned = clean_xml_content(xml_content)

    if not cleaned:
        return None

    try:
        return ET.fromstring(cleaned)
    except ET.ParseError as e:
        logger.warning(f"XML parse error: {e}")
        return None


def extract_xml_section(text: str, start_tag: str, end_tag: str) -> str | None:
    """
    Extract a section from text based on start and end tags.

    Args:
        text: The text to search
        start_tag: The starting tag (e.g., "<hierarchy>")
        end_tag: The ending tag (e.g., "</hierarchy>")

    Returns:
        Extracted section including tags, or None if not found
    """
    start_idx = text.find(start_tag)
    if start_idx == -1:
        return None

    end_idx = text.find(end_tag, start_idx)
    if end_idx == -1:
        return None

    return text[start_idx : end_idx + len(end_tag)]


def xml_to_dict(element: ET.Element) -> dict:
    """
    Convert an XML Element to a dictionary.

    Args:
        element: The XML element to convert

    Returns:
        Dictionary representation of the XML
    """
    result = {}

    # Add attributes
    if element.attrib:
        result.update(element.attrib)

    # Add text content
    if element.text and element.text.strip():
        result["text"] = element.text.strip()

    # Add tail content (text after the element)
    if element.tail and element.tail.strip():
        result["tail"] = element.tail.strip()

    # Process children
    children = {}
    for child in element:
        child_dict = xml_to_dict(child)
        tag = child.tag.split("}")[-1] if "}" in child.tag else child.tag

        if tag in children:
            if not isinstance(children[tag], list):
                children[tag] = [children[tag]]
            children[tag].append(child_dict)
        else:
            children[tag] = child_dict

    if children:
        result["children"] = children

    return result


def get_element_by_path(root: ET.Element, path: str) -> ET.Element | None:
    """
    Find an element by simple path (e.g., "hierarchy/node/node").

    Args:
        root: Root XML element
        path: Path with tags separated by /

    Returns:
        Found element or None
    """
    current = root
    parts = path.split("/")

    for part in parts:
        if not part:
            continue
        found = False
        for child in current:
            tag = child.tag.split("}")[-1] if "}" in child.tag else child.tag
            if tag == part:
                current = child
                found = True
                break
        if not found:
            return None

    return current

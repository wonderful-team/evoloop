"""
EvoLoop Utilities Package

Common utility functions used across the application.
"""

# Core utilities
from app.utils.async_utils import (
    Debouncer,
    LoopBoundResource,
    TaskGroup,
    Throttler,
    fire_and_forget,
    run_in_parallel,
    run_in_thread,
    run_with_timeout,
    throttle,
)
from app.utils.cache import (
    LRUCache,
    TTLCache,
    cached_property,
    lru_cache,
    ttl_cache,
)
from app.utils.dataclass_helpers import (
    AutoConvertMixin,
    NestedSerializableMixin,
    SerializableMixin,
    from_dict_list,
    to_dict_list,
)
from app.utils.diff import (
    DiffTracker,
    compute_text_diff,
    diff_tracker,
    get_diff_stats,
)
from app.utils.extract import (
    extract_code_block,
    extract_json_block,
    extract_tag_content,
    extract_yaml_block,
    safe_parse_json,
    strip_markdown_code_markers,
)
from app.utils.file_type import (
    get_file_category,
    get_file_extension,
    guess_mime_type,
    is_archive_file,
    is_audio_file,
    is_binary_file,
    is_code_file,
    is_document_file,
    is_image_file,
    is_test_file,
    is_text_file,
    is_video_file,
)
from app.utils.geometry import (
    Bounds,
    calculate_iou,
    clamp_coordinates,
    describe_position,
    format_bounds,
    get_bounds_center,
    is_point_in_bounds,
    normalize_coordinates,
    parse_bounds,
)
from app.utils.hash import (
    compute_file_hash,
    compute_hash,
    compute_md5,
    compute_sha256,
    compute_state_id,
    compute_version_hash,
)
from app.utils.id import gen_short_id, gen_uuid
from app.utils.image import (
    base64_to_image,
    convert_image_format,
    create_thumbnail,
    get_image_dimensions,
    get_image_extension,
    get_image_mime_type,
    image_to_base64,
    image_to_data_url,
    is_valid_image,
    resize_image,
)
from app.utils.json import dumps, loads
from app.utils.logging_helpers import (
    format_dict_for_log,
    format_execution_time,
    format_tool_call,
    normalize_log_content,
    sanitize_sensitive_data,
    truncate_for_log,
)
from app.utils.registry import (
    AutoDiscoverRegistry,
    ClassRegistry,
    HandlerRegistry,
    ListRegistry,
    Registry,
    create_registry,
)
from app.utils.template import render_template
from app.utils.path import (
    cleanup_file,
    ensure_dir,
    find_files,
    get_absolute_path,
    get_file_extension,
    get_filename_without_ext,
    get_relative_path,
    get_unique_filename,
    is_path_readable,
    is_path_writable,
    is_safe_path,
    normalize_path,
    safe_join,
    sanitize_filename,
)
from app.utils.random import (
    ProbabilisticExecutor,
    RandomizedScheduler,
    random_delay_ms,
    random_drift,
    random_drift_2d,
    random_float_range,
    random_int_range,
    should_trigger,
    sleep_ms,
    sleep_with_backoff,
)
from app.utils.retry import (
    RetryContext,
    retry_async,
    retry_operation,
    retry_with_fallback,
)
from app.utils.similarity import (
    calculate_similarity,
    find_all_similar,
    find_similar_file,
    find_similar_string,
    levenshtein_distance,
    normalize_for_comparison,
)
from app.utils.security import (
    SimpleRateLimiter,
    is_path_within_base,
    is_safe_url,
    mask_sensitive_data,
    sanitize_filename,
    sanitize_string,
    validate_bundle_id,
    validate_package_name,
)
from app.utils.serialization import (
    MessageSerializer,
    deserialize_messages,
    safe_json_dumps,
    safe_json_loads,
    safe_serialize,
    serialize_messages,
    to_json_string,
)
from app.utils.template import (
    TemplateRenderer,
    render_template,
    render_template_file,
    render_template_from_dir,
)
from app.utils.controller_response import (
    ContentFormatter,
    ControllerResponse,
    PerceptionsFormatter,
    ProjectManagementFormatter,
    SkillResponse,
    SystemToolsFormatter,
)
from app.utils.text import (
    clean_text,
    extract_code_blocks,
    extract_json_from_markdown,
    html_to_markdown,
    normalize_text,
    truncate_output,
    truncate_text,
)
from app.utils.time import (
    format_duration,
    format_iso_timestamp,
    is_past,
    normalize_timestamp_ms_to_sec,
    normalize_timestamp_sec_to_ms,
    parse_iso_timestamp,
    parse_relative_time,
    time_until,
    utcnow,
)
from app.utils.xml import clean_xml_content, safe_parse_xml

__all__ = [
    # Registry
    "Registry",
    "ListRegistry",
    "ClassRegistry",
    "HandlerRegistry",
    "AutoDiscoverRegistry",
    "create_registry",
    # Dataclass Helpers
    "SerializableMixin",
    "NestedSerializableMixin",
    "AutoConvertMixin",
    "to_dict_list",
    "from_dict_list",
    # Diff
    "DiffTracker",
    "diff_tracker",
    "compute_text_diff",
    "get_diff_stats",
    # Similarity
    "find_similar_string",
    "find_similar_file",
    "calculate_similarity",
    "find_all_similar",
    "levenshtein_distance",
    "normalize_for_comparison",
    # Random Utils
    "random_delay_ms",
    "random_int_range",
    "random_float_range",
    "random_drift",
    "random_drift_2d",
    "should_trigger",
    "sleep_ms",
    "sleep_with_backoff",
    "RandomizedScheduler",
    "ProbabilisticExecutor",
    # Async
    "LoopBoundResource",
    "run_in_thread",
    "run_in_parallel",
    "run_with_timeout",
    "fire_and_forget",
    "throttle",
    "TaskGroup",
    "Debouncer",
    "Throttler",
    # ID
    "gen_uuid",
    "gen_short_id",
    # Hash
    "compute_hash",
    "compute_md5",
    "compute_sha256",
    "compute_file_hash",
    "compute_version_hash",
    "compute_state_id",
    # JSON
    "dumps",
    "loads",
    # Text
    "truncate_text",
    "truncate_output",
    "clean_text",
    "extract_code_blocks",
    "extract_json_from_markdown",
    "html_to_markdown",
    "normalize_text",
    # Extract
    "extract_code_block",
    "extract_json_block",
    "extract_yaml_block",
    "extract_tag_content",
    "safe_parse_json",
    "strip_markdown_code_markers",
    # Time
    "utcnow",
    "format_duration",
    "parse_iso_timestamp",
    "parse_relative_time",
    "format_iso_timestamp",
    "normalize_timestamp_ms_to_sec",
    "normalize_timestamp_sec_to_ms",
    "is_past",
    "time_until",
    # Geometry
    "Bounds",
    "parse_bounds",
    "format_bounds",
    "normalize_coordinates",
    "get_bounds_center",
    "is_point_in_bounds",
    "calculate_iou",
    "describe_position",
    "clamp_coordinates",
    # XML
    "clean_xml_content",
    "safe_parse_xml",
    # File Type
    "is_binary_file",
    "is_text_file",
    "is_image_file",
    "is_video_file",
    "is_audio_file",
    "is_archive_file",
    "is_document_file",
    "is_code_file",
    "is_test_file",
    "get_file_category",
    "get_file_extension",
    "guess_mime_type",
    # Path
    "normalize_path",
    "safe_join",
    "ensure_dir",
    "get_filename_without_ext",
    "get_relative_path",
    "get_absolute_path",
    "find_files",
    "get_unique_filename",
    "is_path_readable",
    "is_path_writable",
    "is_safe_path",
    "sanitize_filename",
    "cleanup_file",
    # Cache
    "TTLCache",
    "LRUCache",
    "ttl_cache",
    "lru_cache",
    "cached_property",
    # Image
    "image_to_base64",
    "base64_to_image",
    "image_to_data_url",
    "get_image_mime_type",
    "get_image_extension",
    "resize_image",
    "get_image_dimensions",
    "convert_image_format",
    "create_thumbnail",
    "is_valid_image",
    # Template
    "render_template",
    "render_template_file",
    "render_template_from_dir",
    "TemplateRenderer",
    # Controller Response
    "ContentFormatter",
    "ControllerResponse",
    "PerceptionsFormatter",
    "ProjectManagementFormatter",
    "SkillResponse",
    "SystemToolsFormatter",
    # Retry
    "retry_async",
    "retry_with_fallback",
    "RetryContext",
    "retry_operation",
    # Security
    "sanitize_filename",
    "is_path_within_base",
    "validate_bundle_id",
    "validate_package_name",
    "is_safe_url",
    "sanitize_string",
    "mask_sensitive_data",
    "SimpleRateLimiter",
    # Serialization
    "serialize_messages",
    "deserialize_messages",
    "MessageSerializer",
    "safe_json_dumps",
    "safe_json_loads",
    "safe_serialize",
    "to_json_string",
    # Logging
    "normalize_log_content",
    "format_tool_call",
    "format_execution_time",
    "truncate_for_log",
    "format_dict_for_log",
    "sanitize_sensitive_data",
]

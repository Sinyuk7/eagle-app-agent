"""Request contract constants and typed results for moodtag."""

from __future__ import annotations

from dataclasses import dataclass, field

SUPPORTED_PROTOCOLS = ("chat", "responses")
DEFAULT_PROTOCOL = "responses"
# Moodtag favors visual interpretation over strict classification; 0.6 keeps output useful
# without making it overly inventive.
DEFAULT_TEMPERATURE = 0.6
QUALITY_TOP_P = 0.85
DEFAULT_TOP_P = QUALITY_TOP_P
DEFAULT_TOP_K = 20
DEFAULT_MIN_P = 0.0

DEFAULT_MAX_TOKENS = 1028
MIN_MAX_TOKENS = 1028

DEFAULT_PRESENCE_PENALTY = 0.3
DEFAULT_REPETITION_PENALTY = 1.0

# False means JSON Mode is enabled by default:
# response_format={"type":"json_object"} is sent unless explicitly disabled.
# Moodtag does not enable thinking mode for this model contract.
DEFAULT_NO_RESPONSE_FORMAT = False


ANNOTATION_FIELDS = ("brief", "elements", "use", "key", "camera", "light_color")
COMMERCIAL_LIST_FIELDS = (
    "visible_text",
    "brand_evidence",
    "product_categories",
)
COMMERCIAL_CONFIDENCE_VALUES = ("confirmed", "probable", "not_assessed")
ANNOTATION_LABELS = {
    "brief": "Brief",
    "elements": "Elements",
    "use": "Use",
    "key": "Key",
    "camera": "Camera",
    "light_color": "LightColor",
    "visible_text": "VisibleText",
    "brand_evidence": "BrandEvidence",
    "product_categories": "ProductCategories",
    "commercial_format_confidence": "CommercialFormatConfidence",
}
DEFAULT_JSON_TEMPLATE = (
    '{"brief":"","elements":[],"use":"","key":"","camera":"",'
    '"light_color":"","tags":[],"use_intents":[]}'
)
EDITORIAL_JSON_TEMPLATE = (
    '{"brief":"","elements":[],"use":"","key":"","camera":"",'
    '"light_color":"","visible_text":[],"brand_evidence":[],'
    '"product_categories":[],"commercial_format_confidence":"not_assessed",'
    '"tags":[],"use_intents":[]}'
)
JSON_TEMPLATE = DEFAULT_JSON_TEMPLATE

USE_INTENT_TAGS = {
    "pose_reference": "pose ref",
    "lighting_reference": "lighting ref",
    "composition_reference": "composition ref",
    "color_reference": "color ref",
    "style_reference": "styling ref",
    "wardrobe_reference": "styling ref",
    "scene_reference": "composition ref",
    "aigc_prompt_reference": "prompt ref",
    "3d_material_reference": "reference",
    "film_language_reference": "moodboard",
}


class CoreError(RuntimeError):
    """Expected request-layer error."""


@dataclass(frozen=True)
class MoodtagAnalysis:
    brief: str
    elements: list[str]
    use: str
    key: str
    camera: str
    light_color: str
    visible_text: list[str] = field(default_factory=list)
    brand_evidence: list[str] = field(default_factory=list)
    product_categories: list[str] = field(default_factory=list)
    commercial_format_confidence: str = "not_assessed"
    tags: list[str] = field(default_factory=list)
    tag_groups: dict[str, list[str]] = field(default_factory=dict)
    use_intents: list[str] = field(default_factory=list)
    rejected_tags: list[str] = field(default_factory=list)
    rejected_use_intents: list[str] = field(default_factory=list)

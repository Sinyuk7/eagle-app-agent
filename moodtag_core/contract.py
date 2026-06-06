"""Request contract constants and typed results for moodtag."""

from __future__ import annotations

from dataclasses import dataclass, field


DEFAULT_BASE_URL = "https://hk.n1n.ai/v1"
DEFAULT_FALLBACK_BASE_URL = "https://api.n1n.ai/v1"
DEFAULT_MODEL = "Qwen3.5-122B-A10B"

DEFAULT_TEMPERATURE = 0.6 ## 你的任务不是 OCR，也不是严格分类，而是“创作素材理解”。因此适度的创造性是有益的。0.6 是一个不错的起点，可以根据实际效果进行微调。
QUALITY_TOP_P = 0.85
DEFAULT_TOP_P = QUALITY_TOP_P
DEFAULT_TOP_K = 20
DEFAULT_MIN_P = 0.0

DEFAULT_MAX_TOKENS = 1028

DEFAULT_PRESENCE_PENALTY = 0.3
DEFAULT_REPETITION_PENALTY = 1.0

# False means JSON Mode is enabled by default:
# response_format={"type":"json_object"} is sent unless explicitly disabled.
# Moodtag does not enable thinking mode for this provider contract.
DEFAULT_NO_RESPONSE_FORMAT = False


ANNOTATION_FIELDS = ("brief", "elements", "use", "key", "camera", "light_color")
ANNOTATION_LABELS = {
    "brief": "Brief",
    "elements": "Elements",
    "use": "Use",
    "key": "Key",
    "camera": "Camera",
    "light_color": "LightColor",
}
JSON_TEMPLATE = (
    '{"brief":"","elements":[],"use":"","key":"","camera":"","light_color":"","tags":[],"use_intents":[]}'
)

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
    tags: list[str] = field(default_factory=list)
    use_intents: list[str] = field(default_factory=list)
    rejected_tags: list[str] = field(default_factory=list)
    rejected_use_intents: list[str] = field(default_factory=list)

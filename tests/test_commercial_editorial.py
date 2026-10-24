import unittest

import moodtag
from moodtag_core.annotation import (
    build_annotation_block,
    has_analysis_annotation,
    parse_annotation_fields,
)
from moodtag_core.contract import CoreError
from moodtag_core.prompts import render_user_prompt
from moodtag_core.response import normalize_analysis_json
from moodtag_core.taxonomy import load_profile_taxonomy, validate_unique_tags


def legacy_payload() -> dict[str, object]:
    return {
        "brief": "女性模特站在白色背景前展示黑色夹克。",
        "elements": ["女性模特", "黑色夹克", "白色背景", "银色耳环", "黑色长裤"],
        "use": "服装廓形与留白构图参考。",
        "key": "无品牌证据，黑白服装对比与大面积留白。",
        "camera": "半身平视，右侧留白。",
        "light_color": "柔和正面光，黑白中性色。",
        "suggest_title": "",
        "tags": ["photo"],
        "use_intents": [],
    }


class CommercialEditorialTests(unittest.TestCase):
    taxonomy = {
        "medium": ["photo"],
        "commercial_format": ["campaign"],
        "channel": ["social media"],
        "visual_role": ["hero image"],
        "layout_intent": ["copy space"],
        "pipeline": ["lighting ref"],
    }

    def test_default_and_editorial_profiles_use_different_json_contracts(self):
        default_prompt = render_user_prompt(self.taxonomy, profile="default")
        editorial_prompt = render_user_prompt(self.taxonomy)

        self.assertNotIn('"visible_text"', default_prompt)
        self.assertNotIn('"commercial_format_confidence"', default_prompt)
        self.assertIn('"visible_text"', editorial_prompt)
        self.assertIn('"brand_evidence"', editorial_prompt)
        self.assertIn('"product_categories"', editorial_prompt)
        self.assertIn('"commercial_format_confidence"', editorial_prompt)

    def test_title_rules_identify_uninformative_names_in_both_profiles(self):
        for profile in ("default", "editorial"):
            prompt = render_user_prompt(self.taxonomy, profile=profile)
            self.assertIn('"收藏到 Campaign"', prompt)
            self.assertIn('"搜索结果页面"', prompt)
            self.assertIn('"Celine"', prompt)
            self.assertIn(
                "Return an empty string only when the original title is already informative",
                prompt,
            )

    def test_legacy_payload_keeps_default_commercial_values_out_of_annotation(self):
        analysis = normalize_analysis_json(
            legacy_payload(), taxonomy=self.taxonomy, max_tags=15
        )
        annotation = build_annotation_block(analysis)

        self.assertEqual(analysis.visible_text, [])
        self.assertEqual(analysis.brand_evidence, [])
        self.assertEqual(analysis.product_categories, [])
        self.assertEqual(analysis.commercial_format_confidence, "not_assessed")
        self.assertNotIn("VisibleText:", annotation)
        self.assertNotIn("CommercialFormatConfidence:", annotation)

    def test_generated_tags_share_profile_validation_and_final_limit(self):
        taxonomy = {"only": ["photo", "fashion", "lighting ref"]}
        payload = {
            **legacy_payload(),
            "tags": ["PHOTO", "fashion", "unknown"],
            "use_intents": ["lighting_reference", "color_reference", "invalid"],
        }
        analysis = normalize_analysis_json(payload, taxonomy=taxonomy, max_tags=2)
        self.assertEqual(analysis.tags, ["photo", "fashion"])
        self.assertEqual(analysis.tag_groups, {"only": ["photo", "fashion"]})
        self.assertEqual(
            analysis.use_intents, ["lighting_reference", "color_reference"]
        )
        self.assertEqual(analysis.rejected_tags, ["unknown", "color ref"])
        self.assertEqual(analysis.rejected_use_intents, ["invalid"])

    def test_derived_tags_outside_profile_are_not_generated(self):
        analysis = normalize_analysis_json(
            {**legacy_payload(), "use_intents": ["color_reference"]},
            taxonomy={"only": ["photo"]},
            max_tags=15,
        )
        self.assertEqual(analysis.tags, ["photo"])
        self.assertEqual(analysis.use_intents, ["color_reference"])
        self.assertEqual(analysis.rejected_tags, ["color ref"])

    def test_case_variant_valid_duplicate_is_not_rejected(self):
        analysis = normalize_analysis_json(
            {**legacy_payload(), "tags": ["photo", "PHOTO"]},
            taxonomy={"only": ["photo"]},
            max_tags=15,
        )
        self.assertEqual(analysis.tags, ["photo"])
        self.assertEqual(analysis.rejected_tags, [])

    def test_commercial_fields_normalize_group_and_round_trip_through_annotation(self):
        payload = {
            **legacy_payload(),
            "visible_text": ["NIKE", "NIKE", "AIR"],
            "brand_evidence": ["NIKE Swoosh，夹克左胸；"],
            "product_categories": ["运动夹克", "运动鞋", "运动鞋"],
            "commercial_format_confidence": "probable",
            "tags": [
                "photo",
                "campaign",
                "social media",
                "hero image",
                "copy space",
            ],
            "use_intents": ["lighting_reference"],
        }
        analysis = normalize_analysis_json(payload, taxonomy=self.taxonomy, max_tags=15)
        annotation = build_annotation_block(analysis)
        fields = parse_annotation_fields(annotation)

        self.assertEqual(analysis.visible_text, ["NIKE", "AIR"])
        self.assertEqual(analysis.brand_evidence, ["NIKE Swoosh，夹克左胸"])
        self.assertEqual(analysis.product_categories, ["运动夹克", "运动鞋"])
        self.assertEqual(analysis.commercial_format_confidence, "probable")
        self.assertEqual(
            analysis.tag_groups,
            {
                "medium": ["photo"],
                "commercial_format": ["campaign"],
                "channel": ["social media"],
                "visual_role": ["hero image"],
                "layout_intent": ["copy space"],
                "pipeline": ["lighting ref"],
            },
        )
        self.assertEqual(fields["VisibleText"], "NIKE；AIR。")
        self.assertEqual(fields["BrandEvidence"], "NIKE Swoosh，夹克左胸。")
        self.assertEqual(fields["ProductCategories"], "运动夹克；运动鞋。")
        self.assertEqual(fields["CommercialFormatConfidence"], "probable")

    def test_legacy_annotation_remains_recognized(self):
        annotation = "\n\n".join(
            [
                "Brief: 女性模特站在白色背景前展示黑色夹克。",
                "Elements: 女性模特；黑色夹克；白色背景。",
                "Use: 服装廓形参考。",
                "Key: 无品牌证据，黑白对比。",
                "Camera: 半身平视。",
                "LightColor: 柔和正面光。",
            ]
        )
        self.assertTrue(has_analysis_annotation(annotation))

    def test_invalid_commercial_confidence_is_rejected(self):
        payload = {**legacy_payload(), "commercial_format_confidence": "high"}
        with self.assertRaisesRegex(CoreError, "commercial_format_confidence"):
            normalize_analysis_json(payload, taxonomy=self.taxonomy, max_tags=15)

    def test_suggest_title_is_strict_but_may_be_empty(self):
        payload = legacy_payload()
        payload["suggest_title"] = ""
        result = normalize_analysis_json(payload, taxonomy=self.taxonomy, max_tags=15)
        self.assertEqual(result.suggest_title, "")
        for invalid in (None, 42):
            with (
                self.subTest(invalid=invalid),
                self.assertRaisesRegex(CoreError, "suggest_title"),
            ):
                normalize_analysis_json(
                    {**payload, "suggest_title": invalid},
                    taxonomy=self.taxonomy,
                    max_tags=15,
                )
        with self.assertRaisesRegex(CoreError, "suggest_title"):
            normalize_analysis_json(
                {
                    key: value
                    for key, value in payload.items()
                    if key != "suggest_title"
                },
                taxonomy=self.taxonomy,
                max_tags=15,
            )

    def test_taxonomy_rejects_duplicate_tag_across_facets(self):
        with self.assertRaisesRegex(CoreError, "appears in both"):
            validate_unique_tags(
                {"genre": ["editorial"], "commercial_format": ["editorial"]}
            )

    def test_taxonomy_rejects_duplicate_tag_within_facet(self):
        with self.assertRaisesRegex(CoreError, "appears more than once"):
            validate_unique_tags({"genre": ["editorial", "editorial"]})

    def test_profiles_own_separate_bundled_taxonomies(self):
        default_taxonomy = load_profile_taxonomy("default")
        editorial_taxonomy = load_profile_taxonomy("editorial")

        self.assertEqual(default_taxonomy["genre"][4], "street fashion")
        self.assertIn("street", default_taxonomy["environment"])
        self.assertNotIn("commercial_format", default_taxonomy)
        self.assertNotIn("channel", default_taxonomy)
        self.assertIn("campaign", editorial_taxonomy["commercial_format"])
        self.assertIn("social content", editorial_taxonomy["commercial_format"])
        self.assertNotIn("key visual", editorial_taxonomy["commercial_format"])
        self.assertEqual(editorial_taxonomy["channel"], ["social media", "ooh"])
        self.assertIn("key visual", editorial_taxonomy["visual_role"])
        self.assertIn("hero image", editorial_taxonomy["visual_role"])
        self.assertIn("copy space", editorial_taxonomy["layout_intent"])
        self.assertNotIn("tvc", editorial_taxonomy["commercial_format"])
        self.assertNotIn("reels", editorial_taxonomy["commercial_format"])

    def test_editorial_prompt_renders_only_editorial_taxonomy(self):
        default_prompt = moodtag.build_prompt(profile="default")
        editorial_prompt = moodtag.build_prompt()

        self.assertNotIn("commercial_format:", default_prompt)
        self.assertIn("commercial_format: campaign", editorial_prompt)
        self.assertIn("channel: social media | ooh", editorial_prompt)
        self.assertIn("Pipeline tags may be selected directly", editorial_prompt)
        self.assertIn(
            "commercial_format supports multiple compatible tags", editorial_prompt
        )
        self.assertIn("Facet cardinality is evidence-driven", editorial_prompt)

    def test_output_protocol_is_kept_in_system_prompt_only(self):
        for profile in ("default", "editorial"):
            prompt = render_user_prompt(self.taxonomy, profile=profile)
            self.assertNotIn("Output rules:", prompt)
            self.assertNotIn("Output MUST be raw JSON only.", prompt)


if __name__ == "__main__":
    unittest.main()

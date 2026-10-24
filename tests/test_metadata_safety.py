from __future__ import annotations

import unittest
from unittest import mock

from moodtag.cli import (
    EagleClient,
    EagleItem,
    TagItemResult,
    merge_item_tags,
    write_analysis_result,
)
from moodtag_core.annotation import (
    analysis_status,
    build_annotation_block,
    has_analysis_annotation,
    remove_analysis_annotation,
    replace_analysis_annotation,
)
from moodtag_core.contract import MoodtagAnalysis


def analysis() -> MoodtagAnalysis:
    return MoodtagAnalysis(
        brief="A portrait",
        elements=["person"],
        use="editorial",
        key="portrait",
        camera="eye level",
        light_color="soft light",
        suggest_title="",
    )


class MetadataSafetyTests(unittest.TestCase):
    def test_generated_annotation_has_reliable_markers(self):
        block = build_annotation_block(analysis())
        self.assertEqual(analysis_status(block), "valid")
        self.assertTrue(has_analysis_annotation(block))
        self.assertEqual(parse_without_markers(block), "A portrait")

    def test_manual_annotation_is_missing_and_ambiguous_is_malformed(self):
        self.assertEqual(analysis_status("Brief: a manual note"), "malformed")
        self.assertEqual(analysis_status("manual note"), "missing")
        self.assertEqual(
            analysis_status(
                "<!-- moodtag:analysis:start -->\nBrief: x\n<!-- moodtag:analysis:end -->"
            ),
            "malformed",
        )

    def test_replace_and_remove_preserve_manual_text(self):
        old = "Manual note\n\n" + build_annotation_block(analysis())
        new = build_annotation_block(
            MoodtagAnalysis(
                brief="A new portrait",
                elements=["person"],
                use="editorial",
                key="portrait",
                camera="eye level",
                light_color="hard light",
                suggest_title="",
            )
        )
        replaced = replace_analysis_annotation(old, new)
        self.assertIn("Manual note", replaced)
        self.assertIn("A new portrait", replaced)
        self.assertNotIn("A portrait", replaced)
        self.assertEqual(remove_analysis_annotation(replaced), "Manual note")

    def test_tags_merge_case_insensitively(self):
        self.assertEqual(
            merge_item_tags(
                ["CELINE", "Editorial"], ["celine", "Outdoor", "Editorial"]
            ),
            ["CELINE", "Editorial", "Outdoor"],
        )

    def test_write_refreshes_latest_metadata_before_update(self):
        original = EagleItem("1", "one.jpg", "jpg", ["old"], [], "manual")
        latest = EagleItem(
            "1", "one.jpg", "jpg", ["old", "new-manual"], [], "manual latest"
        )
        generated = build_annotation_block(analysis())
        result = TagItemResult(
            index=1, item=original, tags=["ai"], annotation=generated
        )
        updates = []

        class Eagle:
            def item_info(self, item_id):
                self.seen = item_id
                return latest

            def update_item(self, item_id, **kwargs):
                updates.append((item_id, kwargs))

        self.assertEqual(write_analysis_result(Eagle(), result), "changed")
        self.assertEqual(updates[0][1]["tags"], ["old", "new-manual", "ai"])
        self.assertIn("manual latest", updates[0][1]["annotation"])

    def test_write_applies_valid_suggestion_with_original_extension(self):
        item = EagleItem("1", "1.jpg", "jpg", [], [], "")
        result = TagItemResult(
            index=1,
            item=item,
            tags=[],
            annotation=build_annotation_block(analysis()),
            suggested_title="黑色皮革夹克",
        )
        updates = []

        class Eagle:
            def item_info(self, _item_id):
                return item

            def update_item(self, item_id, **kwargs):
                updates.append((item_id, kwargs))

        write_analysis_result(Eagle(), result)
        self.assertEqual(updates[0][1]["name"], "黑色皮革夹克.jpg")

    def test_write_skips_rename_when_name_changed_or_suggestion_invalid(self):
        analyzed = EagleItem("1", "1.jpg", "jpg", [], [], "")
        latest = EagleItem("1", "human-title.jpg", "jpg", [], [], "")
        result = TagItemResult(
            index=1,
            item=analyzed,
            annotation=build_annotation_block(analysis()),
            suggested_title="unsafe/name",
        )
        updates = []

        class Eagle:
            def item_info(self, _item_id):
                return latest

            def update_item(self, item_id, **kwargs):
                updates.append(kwargs)

        write_analysis_result(Eagle(), result)
        self.assertNotIn("name", updates[0])

    def test_write_skips_invalid_title_but_keeps_metadata_update(self):
        item = EagleItem("1", "1.jpg", "jpg", [], [], "")
        result = TagItemResult(
            index=1,
            item=item,
            tags=["ai"],
            annotation=build_annotation_block(analysis()),
            suggested_title="bad:name",
        )
        updates = []

        class Eagle:
            def item_info(self, _item_id):
                return item

            def update_item(self, item_id, **kwargs):
                updates.append(kwargs)

        write_analysis_result(Eagle(), result)
        self.assertNotIn("name", updates[0])
        self.assertIn("ai", updates[0]["tags"])
        self.assertIn("Brief:", updates[0]["annotation"])

    def test_update_item_uses_v2_and_omits_unspecified_name(self):
        with mock.patch(
            "moodtag.cli.http_request", return_value={"status": "success"}
        ) as req:
            EagleClient("http://eagle.test").update_item(
                "item", tags=["x"], annotation="a"
            )
        self.assertTrue(req.call_args.args[1].endswith("/api/v2/item/update"))
        self.assertEqual(
            req.call_args.kwargs["json_body"],
            {"id": "item", "tags": ["x"], "annotation": "a"},
        )

    def test_v2_list_items_paginates(self):
        def page(count, offset):
            return {
                "status": "success",
                "data": {
                    "data": [
                        {"id": str(i), "name": f"{i}.jpg", "ext": "jpg"}
                        for i in range(offset, offset + count)
                    ],
                    "total": 1001,
                    "offset": offset,
                    "limit": 1000,
                },
            }

        with mock.patch(
            "moodtag.cli.http_request", side_effect=[page(1000, 0), page(1, 1000)]
        ):
            items = EagleClient().list_items("folder")
        self.assertEqual(len(items), 1001)
        self.assertEqual(items[-1].id, "1000")


def parse_without_markers(annotation: str) -> str:
    from moodtag_core.annotation import extract_brief

    return extract_brief(annotation)


if __name__ == "__main__":
    unittest.main()


class PaginationBoundaryTests(unittest.TestCase):
    def test_v2_exactly_one_page(self):
        response = {
            "status": "success",
            "data": {
                "data": [
                    {"id": str(i), "name": f"{i}.jpg", "ext": "jpg"}
                    for i in range(1000)
                ],
                "total": 1000,
                "offset": 0,
                "limit": 1000,
            },
        }
        with mock.patch("moodtag.cli.http_request", return_value=response):
            self.assertEqual(len(EagleClient().list_items("folder")), 1000)

    def test_load_scope_rejects_complete_result_over_limit(self):
        class Eagle:
            def boards(self):
                return [
                    type(
                        "Board",
                        (),
                        {
                            "id": "folder",
                            "name": "Folder",
                            "path": "Folder",
                            "parent": None,
                        },
                    )()
                ]

            def list_items(self, _folder):
                return [
                    EagleItem(str(i), f"{i}.jpg", "jpg", [], [], "") for i in range(3)
                ]

        from moodtag.cli import MoodtagError, load_board_scope

        with self.assertRaises(MoodtagError):
            load_board_scope(Eagle(), "folder", max_board_items=2)

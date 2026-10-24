"""Generate opt-in synthetic Ollama evaluation boundary fixtures (maintainer-only)."""

from __future__ import annotations

import argparse
import json
from pathlib import Path

from PIL import Image, ImageDraw, ImageFont


def draw_case(case_id: str, output: Path) -> None:
    image = Image.new("RGB", (768, 768), "#eeeae3")
    draw = ImageDraw.Draw(image)
    if case_id == "low-information":
        draw.rectangle((0, 0, 767, 767), fill="#d7d2ca")
        draw.ellipse((300, 330, 468, 498), fill="#d2cfc8")
    elif case_id == "product-only-detail":
        draw.rounded_rectangle((120, 205, 650, 585), radius=48, fill="#803d38")
        draw.arc((235, 115, 535, 420), 180, 360, fill="#3f2826", width=28)
        draw.rectangle((120, 440, 650, 505), fill="#9d554d")
        draw.ellipse((375, 350, 405, 380), fill="#d1ae73")
    elif case_id == "readable-fictional-wordmark":
        draw.rectangle((90, 130, 678, 640), fill="#202a38")
        draw.rectangle((150, 195, 618, 575), outline="#e3d7bd", width=5)
        font = ImageFont.load_default(size=76)
        draw.text((225, 325), "MOODTAG", fill="#f4eee2", font=font)
    elif case_id == "uncertain-material":
        draw.polygon([(200, 170), (570, 170), (670, 585), (100, 585)], fill="#9b8b76")
        for y in range(235, 560, 52):
            draw.line((155, y, 620, y - 8), fill="#b1a18b", width=3)
        draw.ellipse((357, 335, 410, 388), fill="#796c5c")
    image.save(output, format="PNG")


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "output",
        type=Path,
        help="Directory for generated fixtures and private manifest/gold files",
    )
    args = parser.parse_args()
    cases = [
        ("low-information", ["浅灰色均匀背景", "画面中央有低对比度椭圆形"], [], []),
        (
            "product-only-detail",
            ["红棕色手提包形状", "包身有短提手", "正面有金色圆形扣"],
            ["皮革", "真皮"],
            ["handbag", "product detail", "product focus"],
        ),
        (
            "readable-fictional-wordmark",
            ["深蓝色矩形画面", "边框内可读文字 MOODTAG"],
            [],
            ["readable wordmark", "key visual"],
        ),
        (
            "uncertain-material",
            ["棕褐色梯形形状", "表面有平行横向纹理"],
            ["羊毛", "皮革", "麂皮"],
            [],
        ),
    ]
    args.output.mkdir(parents=True, exist_ok=True)
    manifest, gold = [], {}
    for case_id, facts, disallowed, tags in cases:
        path = args.output / f"{case_id}.png"
        draw_case(case_id, path)
        manifest.append({"id": case_id, "path": str(path)})
        gold[case_id] = {
            "visible_facts": facts,
            "acceptable_variants": {},
            "disallowed_claims": disallowed,
            "tags": tags,
        }
    (args.output / "manifest.json").write_text(
        json.dumps(manifest, ensure_ascii=False, indent=2) + "\n"
    )
    (args.output / "gold.json").write_text(
        json.dumps(gold, ensure_ascii=False, indent=2) + "\n"
    )
    print(f"Generated {len(cases)} synthetic boundary cases in {args.output}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

import unittest
from pathlib import Path


class DocumentationContractTests(unittest.TestCase):
    def test_readme_stays_user_focused(self):
        readme = Path("README.md").read_text(encoding="utf-8").lower()
        self.assertNotIn("local-first", readme)
        self.assertNotIn("ollama-primary", readme)
        self.assertNotIn("temperature=", readme)
        self.assertNotIn("top_p", readme)
        self.assertNotIn("prompt_eval_count", readme)
        self.assertIn("model-setup.md", readme)
        self.assertIn("cli-reference.md", readme)

Moodtag for Apple Silicon

1. Double-click the .pkg file and finish the macOS installer.
2. Open Terminal.
3. Run: moodtag --help
4. Start tagging with: moodtag <board-url-or-id>

If macOS blocks the package because its developer cannot be verified, control-click
the .pkg, choose Open, then confirm. You can also use System Settings > Privacy &
Security > Open Anyway.

The installer includes its own Python runtime. Python, uv, npm, and Homebrew are
not required to use moodtag.

The first tagging run asks for the vision API key and stores it in:
~/.config/moodtag/.env

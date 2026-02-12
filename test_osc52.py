#!/usr/bin/env python3
"""Diagnostic: test clipboard methods. Run directly in terminal."""

import subprocess
import shutil

TEXT = "ncview_clipboard_test"

if shutil.which("pbcopy"):
    subprocess.run(["pbcopy"], input=TEXT.encode(), check=True)
    print(f"Sent '{TEXT}' to pbcopy. Try Cmd+V now.")
else:
    print("pbcopy not found")

#!/usr/bin/env python3
"""Simple Modal test"""

import modal

app = modal.App("test-simple")

@app.function()
def hello(name: str) -> str:
    return f"Hello {name}!"

@app.local_entrypoint()
def main():
    print("📤 Starting test...")
    result = hello.remote("World")
    print(f"✅ Result: {result}")

if __name__ == "__main__":
    main()

# Sample Markdown File

This is a test file for the **ncview** markdown viewer.

## Text Formatting

Here's some **bold text**, *italic text*, and `inline code`. You can also do ~~strikethrough~~ and ***bold italic***.

## Lists

### Unordered
- First item
- Second item
  - Nested item
  - Another nested item
- Third item

### Ordered
1. Step one
2. Step two
3. Step three

## Code Blocks

```python
def fibonacci(n: int) -> int:
    """Return the nth Fibonacci number."""
    if n <= 1:
        return n
    a, b = 0, 1
    for _ in range(2, n + 1):
        a, b = b, a + b
    return b
```

```bash
# Install ncview
pip install ncview

# Run it
ncview /path/to/directory
```

## Table

| Feature       | Status | Priority |
|---------------|--------|----------|
| File browser  | Done   | High     |
| Parquet view  | Done   | High     |
| JSON tree     | Done   | Medium   |
| Markdown view | Done   | Medium   |
| Delete files  | Done   | Low      |

## Blockquote

> "The best way to predict the future is to invent it."
> — Alan Kay

## Links and Images

Check out [ncview on GitHub](https://github.com/dannyfriar/ncview) for more info.

## Horizontal Rule

---

## Nested Content

Here's a more complex example with mixed content:

1. **Setup**: Install dependencies
   ```
   uv pip install -e ".[dev]"
   ```
2. **Run**: Launch the browser
   - Use `j`/`k` to navigate
   - Press `Enter` to preview
3. **Done**: Press `q` to quit

That's it! Enjoy browsing files in the terminal.

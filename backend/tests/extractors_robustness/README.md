# Extractor Robustness Test Suite

This comprehensive test suite validates the robustness of all 11 document extractors in the EvoLoop knowledge base system.

## Test Structure

```
tests/extractors_robustness/
├── __init__.py              # Test utilities and base classes
├── base.py                  # BaseTestCase and file generators
├── test_text.py             # PlainText, Markdown, CodeDoc extractors
├── test_html.py             # HTML extractor (XSS, malformed HTML)
├── test_pdf.py              # PDF extractors (pdfplumber + PyPDF2 fallback)
├── test_office.py           # Word, Excel, PowerPoint extractors
├── test_image.py            # Image OCR extractors
├── test_registry.py         # ExtractorRegistry integration tests
└── README.md               # This file
```

## 11 Extractors Under Test

| Extractor | Formats | Key Robustness Tests |
|-----------|---------|---------------------|
| PlainText | .txt, .log, .md | Empty files, binary data, large files, encoding |
| Markdown | .md, .markdown | Frontmatter parsing, malformed YAML, XSS |
| CodeDoc | .py, .js, .ts, .java | Language detection, syntax errors, mixed content |
| HTML | .html, .htm | Script removal, malformed HTML, nested elements |
| PDF-Pdfplumber | .pdf | Corrupted PDFs, encrypted PDFs, image-only PDFs |
| PDF-PyPDF2 | .pdf (fallback) | Same as above with fallback handling |
| Word | .docx, .doc | Corrupted documents, password protected, macros |
| Excel | .xlsx, .xls | Large sheets, formulas, merged cells, empty sheets |
| PowerPoint | .pptx, .ppt | Empty slides, embedded media, corrupted structure |
| ImageOCR | .png, .jpg, .tiff | No text images, corrupted images, large images |
| ScreenshotOCR | .png, .jpg | UI element detection, multiple windows |

## Common Test Cases (All Extractors)

### Empty Files
- Zero-byte files
- Whitespace only
- Newline-only content
- Null bytes

### Corrupted Data
- Random binary data
- Truncated files
- Incorrect magic bytes
- Missing end markers

### Encoding Issues
- UTF-8 (with/without BOM)
- UTF-16
- ISO-8859-1
- GB2312
- Shift-JIS
- Invalid UTF-8 sequences

### Large Files
- 1 MB files
- 10 MB files
- 50 MB files
- 100 MB files (where applicable)

### Malicious Content
- XSS attempts in HTML
- Path traversal in filenames
- Null bytes in filenames
- Very long filenames
- Control characters

## Running the Tests

### Run All Tests
```bash
cd /Users/huangjinhuan/项目/develop-assistant.cn/evoloop/backend
python -m pytest tests/extractors_robustness/ -v
```

### Run Specific Test Module
```bash
python -m pytest tests/extractors_robustness/test_text.py -v
python -m pytest tests/extractors_robustness/test_html.py -v
python -m pytest tests/extractors_robustness/test_pdf.py -v
```

### Run Specific Test
```bash
python -m pytest tests/extractors_robustness/test_text.py::TextRobustnessTest::test_empty_files -v
```

### Quick Smoke Test
```bash
python test_robustness_quick.py
```

## Expected Behavior

All extractors should:

1. **Never crash** - Catch all exceptions and return partial results
2. **Handle empty files** - Return empty documents with metadata
3. **Handle corrupted data** - Return best-effort extraction or error document
4. **Limit resource usage** - Respect memory limits and timeouts
5. **Sanitize output** - Remove malicious content, escape special characters
6. **Handle large files** - Process in chunks or with size limits
7. **Support timeout** - Cancel long-running extractions

## Test Utilities

### File Generators (`base.py`)

```python
# Create test files programmatically
create_empty_file()        # Zero bytes
create_text_file(size)     # Specific size text
create_binary_garbage()    # Random binary data
create_corrupted_file(fmt) # Format-specific corruption
```

### Assertion Helpers (`base.py`)

```python
# Document validation
assert_document_valid(doc)           # Basic validation
assert_no_exception(func)            # Exception-free execution
assert_within_memory(func, limit)    # Memory constraint
assert_within_time(func, timeout)    # Timeout constraint
```

## Architecture Notes

- **BaseTestCase**: Common test infrastructure for all extractor tests
- **Async Support**: All tests use `async/await` patterns
- **Resource Cleanup**: Automatic cleanup of temp files via `tempfile`
- **Memory Limits**: Tests verify memory usage stays within bounds
- **Timeout Handling**: Long-running operations should respect timeouts

## Coverage Summary

| Category | Tests | Status |
|----------|-------|--------|
| Empty Files | 33 tests | ✅ Complete |
| Corrupted Data | 33 tests | ✅ Complete |
| Encoding Issues | 55 tests | ✅ Complete |
| Large Files | 44 tests | ✅ Complete |
| Malicious Content | 22 tests | ✅ Complete |
| Format-Specific | 77 tests | ✅ Complete |
| **Total** | **~264 tests** | ✅ Complete |

## Integration with CI/CD

```yaml
# .github/workflows/test.yml
- name: Run Extractor Robustness Tests
  run: |
    cd backend
    python -m pytest tests/extractors_robustness/ \
      --tb=short \
      -q \
      --timeout=300
```

## Debugging Failed Tests

1. Check logs in `tests/extractors_robustness/logs/`
2. Review generated test files in `/tmp/`
3. Run with `-v --capture=no` for detailed output
4. Use `--pdb` to debug failures interactively

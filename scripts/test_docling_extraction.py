#!/usr/bin/env python3
"""
Test Docling PDF extraction on Oct 6, 2025 San Rafael agenda packet

Validates that Docling can extract structured content from municipal
agenda PDFs better than regex-based splitting.
"""

from docling.document_converter import DocumentConverter
import sys

def test_oct6_extraction():
    """Test Docling on Oct 6 wildfire case study"""

    # Oct 6 agenda packet URL (direct PDF link)
    pdf_url = "https://storage.googleapis.com/proudcity/sanrafaelca/2025/10/Agenda-Packet-2025-10-06.pdf"

    print("🔍 Testing Docling PDF Extraction")
    print(f"PDF: Oct 6, 2025 City Council Agenda Packet")
    print(f"URL: {pdf_url}\n")

    # Initialize converter
    print("Initializing DocumentConverter...")
    converter = DocumentConverter()

    # Convert PDF
    print("Converting PDF to structured format...")
    result = converter.convert(pdf_url)

    # Export to markdown
    print("\n✅ Conversion complete!")
    print("\n" + "="*70)
    print("MARKDOWN OUTPUT (first 5000 chars):")
    print("="*70)

    markdown = result.document.export_to_markdown()
    print(markdown[:5000])

    print("\n" + "="*70)
    print(f"Total markdown length: {len(markdown):,} characters")
    print("="*70)

    # Check if wildfire item is present
    if "wildfire" in markdown.lower() or "measure c" in markdown.lower():
        print("\n✅ SUCCESS: Found wildfire-related content!")
    else:
        print("\n⚠️  WARNING: Wildfire content not found in first 5000 chars")

    # Save full markdown
    output_file = "data/pilot/oct6_docling_test.md"
    with open(output_file, 'w') as f:
        f.write(markdown)
    print(f"\n📄 Full markdown saved to: {output_file}")

    return markdown

if __name__ == "__main__":
    try:
        markdown = test_oct6_extraction()
        print("\n✅ Test complete!")
        sys.exit(0)
    except Exception as e:
        print(f"\n❌ Error: {type(e).__name__}: {e}")
        import traceback
        traceback.print_exc()
        sys.exit(1)

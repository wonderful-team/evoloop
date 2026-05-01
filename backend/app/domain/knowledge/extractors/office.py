"""
Office document extractors for Word, Excel, and PowerPoint files.
"""

import logging
from typing import BinaryIO

from app.domain.knowledge.extractors.base import BaseExtractor
from app.domain.knowledge.models import MarkdownDocument, ExtractionError

logger = logging.getLogger(__name__)


class WordExtractor(BaseExtractor):
    """
    Extractor for Microsoft Word documents (.docx).
    
    Extracts text content, preserving document structure including
    headings, paragraphs, lists, and tables.
    
    Requires: pip install python-docx
    """
    
    @property
    def name(self) -> str:
        return "word"
    
    def priority(self) -> int:
        """High priority for Word docs."""
        return 10
    
    def supports(self, mime_type: str, filename: str) -> bool:
        """Check if file is a Word document."""
        ext = self._get_file_extension(filename)
        if ext == '.docx':
            return True
        if mime_type in {
            'application/vnd.openxmlformats-officedocument.wordprocessingml.document',
            'application/msword'
        }:
            return True
        return False
    
    async def is_available(self) -> bool:
        """Check if python-docx is installed."""
        try:
            import docx
            return True
        except ImportError:
            return False
    
    async def extract(self, file: BinaryIO, filename: str) -> MarkdownDocument:
        """Extract content from Word document."""
        try:
            import docx
        except ImportError:
            raise ExtractionError(
                "python-docx not installed. Run: pip install python-docx",
                source=filename
            )
        
        temp_path = self._save_temp(file, suffix='.docx')
        
        try:
            doc = docx.Document(temp_path)
            
            # Extract metadata
            metadata = {
                "paragraph_count": len(doc.paragraphs),
                "table_count": len(doc.tables),
                "core_properties": {}
            }
            
            # Try to get core properties
            try:
                core_props = doc.core_properties
                metadata["core_properties"] = {
                    "title": core_props.title or "",
                    "author": core_props.author or "",
                    "subject": core_props.subject or "",
                    "keywords": core_props.keywords or "",
                    "created": str(core_props.created) if core_props.created else "",
                    "modified": str(core_props.modified) if core_props.modified else "",
                }
            except Exception:
                pass
            
            # Extract content
            lines = []
            title = metadata["core_properties"].get("title", "")
            
            if title:
                lines.append(f"# {title}\n")
            
            # Process paragraphs
            for para in doc.paragraphs:
                if para.text.strip():
                    # Check style for heading
                    style_name = para.style.name.lower() if para.style else ""
                    
                    if 'heading' in style_name or '标题' in style_name:
                        # Determine heading level
                        level = 1
                        for i in range(1, 10):
                            if f'heading {i}' in style_name or f'标题 {i}' in style_name:
                                level = i
                                break
                        lines.append(f"{'#' * level} {para.text}\n")
                    else:
                        lines.append(f"{para.text}\n")
            
            # Process tables
            for i, table in enumerate(doc.tables, 1):
                lines.append(f"\n## Table {i}\n")
                lines.append(self._table_to_markdown(table))
                lines.append("")
            
            content = '\n'.join(lines)
            
            return MarkdownDocument(
                content=content,
                source=filename,
                mime_type="application/vnd.openxmlformats-officedocument.wordprocessingml.document",
                metadata=metadata
            )
        
        finally:
            import os
            os.unlink(temp_path)
    
    def _table_to_markdown(self, table) -> str:
        """Convert Word table to Markdown."""
        lines = []
        
        for i, row in enumerate(table.rows):
            cells = [cell.text.strip() for cell in row.cells]
            lines.append('| ' + ' | '.join(cells) + ' |')
            
            # Add separator after first row
            if i == 0:
                lines.append('| ' + ' | '.join(['---'] * len(cells)) + ' |')
        
        return '\n'.join(lines)


class ExcelExtractor(BaseExtractor):
    """
    Extractor for Excel spreadsheets (.xlsx, .xls).
    
    Converts worksheets to Markdown tables.
    
    Requires: pip install openpyxl
    """
    
    @property
    def name(self) -> str:
        return "excel"
    
    def priority(self) -> int:
        return 10
    
    def supports(self, mime_type: str, filename: str) -> bool:
        """Check if file is an Excel spreadsheet."""
        ext = self._get_file_extension(filename)
        if ext in ('.xlsx', '.xls'):
            return True
        if mime_type in {
            'application/vnd.openxmlformats-officedocument.spreadsheetml.sheet',
            'application/vnd.ms-excel'
        }:
            return True
        return False
    
    async def is_available(self) -> bool:
        """Check if openpyxl is installed."""
        try:
            import openpyxl
            return True
        except ImportError:
            return False
    
    async def extract(self, file: BinaryIO, filename: str) -> MarkdownDocument:
        """Extract content from Excel file."""
        try:
            import openpyxl
        except ImportError:
            raise ExtractionError(
                "openpyxl not installed. Run: pip install openpyxl",
                source=filename
            )
        
        temp_path = self._save_temp(file, suffix='.xlsx')
        
        try:
            wb = openpyxl.load_workbook(temp_path, data_only=True)
            
            lines = []
            lines.append(f"# {filename}\n")
            
            metadata = {
                "sheet_count": len(wb.sheetnames),
                "sheet_names": wb.sheetnames,
            }
            
            # Process each worksheet
            for sheet_name in wb.sheetnames:
                ws = wb[sheet_name]
                lines.append(f"## Sheet: {sheet_name}\n")
                
                # Convert to markdown table
                rows = []
                max_row = min(ws.max_row, 100)  # Limit to 100 rows per sheet
                max_col = min(ws.max_column, 20)  # Limit to 20 columns
                
                for row_idx in range(1, max_row + 1):
                    row_data = []
                    for col_idx in range(1, max_col + 1):
                        cell = ws.cell(row=row_idx, column=col_idx)
                        value = cell.value
                        if value is None:
                            value = ""
                        row_data.append(str(value))
                    
                    rows.append('| ' + ' | '.join(row_data) + ' |')
                    
                    # Add separator after first row
                    if row_idx == 1:
                        rows.append('| ' + ' | '.join(['---'] * max_col) + ' |')
                
                lines.append('\n'.join(rows))
                lines.append("")
            
            content = '\n'.join(lines)
            
            return MarkdownDocument(
                content=content,
                source=filename,
                mime_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
                metadata=metadata
            )
        
        finally:
            import os
            os.unlink(temp_path)


class PowerPointExtractor(BaseExtractor):
    """
    Extractor for PowerPoint presentations (.pptx).
    
    Extracts text content from slides.
    
    Requires: pip install python-pptx
    """
    
    @property
    def name(self) -> str:
        return "powerpoint"
    
    def priority(self) -> int:
        return 10
    
    def supports(self, mime_type: str, filename: str) -> bool:
        """Check if file is a PowerPoint presentation."""
        ext = self._get_file_extension(filename)
        if ext == '.pptx':
            return True
        if mime_type in {
            'application/vnd.openxmlformats-officedocument.presentationml.presentation',
            'application/vnd.ms-powerpoint'
        }:
            return True
        return False
    
    async def is_available(self) -> bool:
        """Check if python-pptx is installed."""
        try:
            import pptx
            return True
        except ImportError:
            return False
    
    async def extract(self, file: BinaryIO, filename: str) -> MarkdownDocument:
        """Extract content from PowerPoint file."""
        try:
            import pptx
        except ImportError:
            raise ExtractionError(
                "python-pptx not installed. Run: pip install python-pptx",
                source=filename
            )
        
        temp_path = self._save_temp(file, suffix='.pptx')
        
        try:
            prs = pptx.Presentation(temp_path)
            
            lines = []
            lines.append(f"# {filename}\n")
            
            metadata = {
                "slide_count": len(prs.slides),
                "slide_width": prs.slide_width,
                "slide_height": prs.slide_height,
            }
            
            # Extract text from each slide
            for i, slide in enumerate(prs.slides, 1):
                lines.append(f"## Slide {i}\n")
                
                for shape in slide.shapes:
                    if shape.text.strip():
                        lines.append(shape.text.strip())
                        lines.append("")
                
                lines.append("")
            
            content = '\n'.join(lines)
            
            return MarkdownDocument(
                content=content,
                source=filename,
                mime_type="application/vnd.openxmlformats-officedocument.presentationml.presentation",
                metadata=metadata
            )
        
        finally:
            import os
            os.unlink(temp_path)

"""
OCR Provider - Extract text elements using OCR.

Uses EasyOCR (lighter weight) or PaddleOCR for text detection.
Falls back gracefully if OCR libraries are not installed.
"""

import logging
import os
from typing import Any

from app.domain.tools.environment.perception.base import (
    ElementType,
    PerceptionProvider,
    PerceptionResult,
    UIElement,
)

logger = logging.getLogger(__name__)

# Lazy imports for optional dependencies
_ocr_engine = None
_ocr_type = None


def _get_ocr_engine():
    """Lazy-load OCR engine with fallback."""
    global _ocr_engine, _ocr_type
    
    if _ocr_engine is not None:
        return _ocr_engine, _ocr_type
    
    # Try EasyOCR first (lighter weight)
    try:
        import easyocr
        _ocr_engine = easyocr.Reader(['ch_sim', 'en'], gpu=False)
        _ocr_type = "easyocr"
        logger.info("OCR Provider: Using EasyOCR")
        return _ocr_engine, _ocr_type
    except ImportError:
        pass
    
    # Try PaddleOCR
    try:
        from paddleocr import PaddleOCR
        _ocr_engine = PaddleOCR(use_angle_cls=True, lang='ch', show_log=False)
        _ocr_type = "paddleocr"
        logger.info("OCR Provider: Using PaddleOCR")
        return _ocr_engine, _ocr_type
    except ImportError:
        pass
    
    logger.warning("OCR Provider: No OCR library available. Install with: pip install easyocr")
    return None, None


class OCRProvider(PerceptionProvider):
    """
    Perception provider using OCR for text detection.
    
    This provider extracts text elements from screenshots,
    useful as a fallback or supplement to native accessibility APIs.
    """
    
    @property
    def name(self) -> str:
        return "ocr"
    
    @property
    def cost(self) -> float:
        return 0.001  # Very cheap - local processing
    
    async def is_available(self) -> bool:
        """Check if OCR library is installed."""
        engine, _ = _get_ocr_engine()
        return engine is not None
    
    async def extract(
        self,
        screenshot_path: str | None = None,
        device_id: str | None = None,
    ) -> PerceptionResult:
        """
        Extract text elements from screenshot using OCR.
        
        Args:
            screenshot_path: Path to screenshot image
            device_id: Not used
            
        Returns:
            PerceptionResult with text elements
        """
        import time
        start = time.time()
        
        if not screenshot_path or not os.path.exists(screenshot_path):
            return PerceptionResult(
                elements=[],
                source=self.name,
                metadata={"error": "No screenshot provided"}
            )
        
        engine, ocr_type = _get_ocr_engine()
        if engine is None:
            return PerceptionResult(
                elements=[],
                source=self.name,
                metadata={"error": "OCR not available"}
            )
        
        elements = []
        element_id = 0
        
        try:
            if ocr_type == "easyocr":
                results = engine.readtext(screenshot_path)
                for bbox, text, confidence in results:
                    if confidence < 0.3:  # Skip low confidence
                        continue
                    
                    # bbox is [[x1,y1], [x2,y1], [x2,y2], [x1,y2]]
                    x1, y1 = bbox[0]
                    x2, y2 = bbox[2]
                    
                    element = UIElement(
                        id=element_id,
                        text=text,
                        x=int((x1 + x2) / 2),
                        y=int((y1 + y2) / 2),
                        width=int(x2 - x1),
                        height=int(y2 - y1),
                        element_type=ElementType.TEXT,
                        clickable=True,  # Assume clickable
                        confidence=float(confidence),
                        source=self.name,
                    )
                    elements.append(element)
                    element_id += 1
            
            elif ocr_type == "paddleocr":
                results = engine.ocr(screenshot_path, cls=True)
                if results and results[0]:
                    for line in results[0]:
                        bbox, (text, confidence) = line
                        if confidence < 0.3:
                            continue
                        
                        x1, y1 = bbox[0]
                        x2, y2 = bbox[2]
                        
                        element = UIElement(
                            id=element_id,
                            text=text,
                            x=int((x1 + x2) / 2),
                            y=int((y1 + y2) / 2),
                            width=int(x2 - x1),
                            height=int(y2 - y1),
                            element_type=ElementType.TEXT,
                            clickable=True,
                            confidence=float(confidence),
                            source=self.name,
                        )
                        elements.append(element)
                        element_id += 1
        
        except Exception as e:
            logger.error(f"OCR extraction failed: {e}")
            return PerceptionResult(
                elements=[],
                source=self.name,
                metadata={"error": str(e)}
            )
        
        latency = (time.time() - start) * 1000
        logger.info(f"[OCR] Extracted {len(elements)} text elements in {latency:.0f}ms")
        
        return PerceptionResult(
            elements=elements,
            screenshot_path=screenshot_path,
            source=self.name,
            latency_ms=latency,
        )


# Singleton
ocr_provider = OCRProvider()

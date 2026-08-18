import logging
import os
from enum import Enum

from app.constants import EXTENSION_MAP, SOFTWARE_DIRECTORIES, SOFTWARE_INDICATORS

logger = logging.getLogger(__name__)


class ProjectType(Enum):
    SOFTWARE = "software"
    CONTENT = "content"
    UNKNOWN = "unknown"


class ProjectClassifier:
    """
    Classifies a project directory based on file content and structure.
    Used to gate resource-intensive indexing steps (API/DB extraction).
    """

    SOFTWARE_MARKERS = SOFTWARE_INDICATORS | SOFTWARE_DIRECTORIES
    CODE_EXTENSIONS = set(EXTENSION_MAP.keys())

    def classify(self, root_path: str) -> ProjectType:
        """
        Determine if the project is primarily SOFTWARE (code-based) or CONTENT (docs/images).
        Sync operation as it's just filesystem metadata check usually.
        """
        if not os.path.exists(root_path):
            return ProjectType.UNKNOWN

        try:
            # 1. Check for Strong Indicators (Config files) in Root using unified traverser
            from app.core.file import FileTraverser

            entries = {entry.name for entry in FileTraverser.list_entries(root_path)}
            intersection = self.SOFTWARE_MARKERS.intersection(entries)

            if intersection:
                logger.info(f"[Classifier] Classified {root_path} as SOFTWARE (Indicators: {intersection})")
                return ProjectType.SOFTWARE

            # 2. Check for Code Files (Deep Scan but shallow depth)
            # Scan top 2 levels for code files using unified traverser.
            code_file_count = 0
            from app.core.file import FileTraverser, TraverseOptions

            options = TraverseOptions(max_depth=2)
            for full_path in FileTraverser.walk(root_path, options):
                _, ext = os.path.splitext(full_path)
                if ext in self.CODE_EXTENSIONS:
                    code_file_count += 1
                    if code_file_count >= 3:  # Threshold
                        logger.info(f"[Classifier] Classified {root_path} as SOFTWARE (Found code files)")
                        return ProjectType.SOFTWARE

            logger.info(f"[Classifier] Classified {root_path} as CONTENT")
            return ProjectType.CONTENT

        except Exception as e:
            logger.exception(f"Classification failed: {e}")
            return ProjectType.UNKNOWN


# Global Instance
project_classifier = ProjectClassifier()

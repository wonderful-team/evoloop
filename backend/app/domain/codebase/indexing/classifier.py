import logging
import os
from enum import Enum

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

    SOFTWARE_INDICATORS = {
        # Files
        "package.json", "go.mod", "pom.xml", "build.gradle", "requirements.txt",
        "Cargo.toml", "Gemfile", "composer.json", "Makefile",
        "tsconfig.json", "pyproject.toml",
        # Directories
        "src", "app", "lib", "pkg", "cmd"
    }

    CODE_EXTENSIONS = {
        ".py", ".js", ".ts", ".go", ".java", ".cpp", ".c", ".h", ".rs", ".php", ".rb", ".kt", ".swift"
    }

    def classify(self, root_path: str) -> ProjectType:
        """
        Determine if the project is primarily SOFTWARE (code-based) or CONTENT (docs/images).
        Sync operation as it's just filesystem metadata check usually.
        """
        if not os.path.exists(root_path):
            return ProjectType.UNKNOWN

        try:
            # 1. Check for Strong Indicators (Config files) in Root
            entries = set(os.listdir(root_path))
            intersection = self.SOFTWARE_INDICATORS.intersection(entries)

            if intersection:
                logger.info(f"[Classifier] Classified {root_path} as SOFTWARE (Indicators: {intersection})")
                return ProjectType.SOFTWARE

            # 2. Check for Code Files (Deep Scan but shallow depth)
            # Scan top 2 levels for code files.
            code_file_count = 0
            for root, dirs, files in os.walk(root_path):
                # Depth check
                depth = root[len(root_path):].count(os.sep)
                if depth > 2:
                    # Don't go deep
                    del dirs[:]
                    continue

                for f in files:
                    _, ext = os.path.splitext(f)
                    if ext in self.CODE_EXTENSIONS:
                        code_file_count += 1
                        if code_file_count >= 3:  # Threshold
                            logger.info(f"[Classifier] Classified {root_path} as SOFTWARE (Found code files)")
                            return ProjectType.SOFTWARE

            logger.info(f"[Classifier] Classified {root_path} as CONTENT")
            return ProjectType.CONTENT

        except Exception as e:
            logger.error(f"Classification failed: {e}")
            return ProjectType.UNKNOWN


# Global Instance
project_classifier = ProjectClassifier()

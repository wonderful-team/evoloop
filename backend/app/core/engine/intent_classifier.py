"""
Intent Classifier - Semantic routing using Adaptive Classifier.

Leverages 'adaptive-classifier' for continuous learning and semantic understanding.
Bypasses LLM routing for high-confidence patterns, reducing latency significantly.
Falls back to LLM-based routing for ambiguous requests.
"""

import logging

from adaptive_classifier import AdaptiveClassifier

logger = logging.getLogger(__name__)


class IntentClassifier:
    """
    Semantic intent classifier using Adaptive Classifier.
    
    Features:
    1. Semantic Understanding: Uses embeddings to understand context (not just keywords)
    2. Continuous Learning: Can add new intents dynamically
    3. Multi-language Support: Inherits from underlying transformer model
    """

    _model: AdaptiveClassifier | None = None

    # Initial training data for bootstrapping
    INITIAL_INTENTS = {
        # Direct execution intents (bypass Supervisor LLM)
        "chat": [
            "hello", "hi", "你好", "早上好", "晚上好", "hey",
            "what's up", "how are you", "闲聊", "聊天", "say hi",
            "thanks", "谢谢", "goodbye", "再见", "byebye"
        ],
        "browser_executor": [
            "open browser", "search on google", "browse website", "navigate to",
            "打开浏览器", "搜索一下", "打开网页", "帮我搜", "上网查",
            "visit this url", "go to this website", "look up online"
        ],
        "computer_executor": [
            "open application", "click on screen", "take screenshot",
            "打开应用", "点击屏幕", "截图", "操作电脑", "打开文件管理器",
            "use mouse", "type text", "press key"
        ],
        "mobile_executor": [
            "open app on phone", "swipe screen", "tap button",
            "打开手机应用", "滑动屏幕", "点击按钮", "操作手机",
            "install app", "安装应用", "控制手机"
        ],
        # Specialist node intents
        "documenter": [
            "generate wiki", "create documentation", "write readme",
            "生成文档", "创建wiki", "编写说明书", "更新文档", "写个使用手册", "项目结构介绍"
        ],
        "coder": [
            "fix bug", "implement feature", "write function", "refactor code",
            "修复这个错误", "实现一个功能", "编写代码", "重构这个类", "add a new endpoint",
            "写一个登录页面", "帮我写代码", "优化这段逻辑", "添加一个接口"
        ],
        "deep_researcher": [
            "research about AI", "analyze the market", "find out how transformers work",
            "调研一下", "分析竞品", "深度研究", "what is retrieval augmented generation",
            "帮我查一下资料", "搜索一下", "了解一下这个技术"
        ],
        "planner": [
            "plan the system architecture", "design the database schema",
            "规划系统架构", "设计数据库", "制定开发计划", "拆解这个任务"
        ],
        "requirement_analyst": [
            "I want to build an app", "create a CRM system",
            "我想做一个小程序", "开发一个电商系统", "需求分析", "梳理一下需求"
        ]
    }


    MIN_CONFIDENCE = 0.35  # Calibrated for multilingual model embeddings

    @classmethod
    def get_model(cls) -> AdaptiveClassifier:
        """Lazy load the model singleton."""
        if cls._model is None:
            logger.info("[IntentClassifier] Initializing Adaptive Classifier...")
            # Initialize with efficient default model
            cls._model = AdaptiveClassifier(
                model_name='sentence-transformers/paraphrase-multilingual-MiniLM-L12-v2',  # Multilingual support (CN/EN)
                device='cpu'  # Force CPU for stability on standard deployments
            )

            # Bootstrap with initial intents if not already loaded/persisted
            # Note: In a real persistence scenario, we'd load from disk.
            # For now, we fit on startup roughly. Real usage would perform this once.
            logger.info("[IntentClassifier] Bootstrapping initial intents...")

            # Prepare batch data for efficient adding
            texts = []
            labels = []
            for label, examples in cls.INITIAL_INTENTS.items():
                texts.extend(examples)
                labels.extend([label] * len(examples))

            if texts:
                logger.info(f"[IntentClassifier] Adding {len(texts)} examples for {len(set(labels))} classes from {list(set(labels))}")
                cls._model.add_examples(texts, labels)

            logger.info("[IntentClassifier] Initialization complete.")

        return cls._model

    @classmethod
    def classify(cls, message: str) -> str | None:
        """
        Classify user message and return target node if confident.
        """
        if not message or len(message.strip()) < 3:
            return None

        try:
            # Fetch Dynamic Threshold
            # We import here to avoid circular imports during class definition time if any
            from app.domain.system.service import SystemConfigService

            # Default to class constant (0.35)
            # Users can tune this between 0.0 (aggressive) and 1.0 (conservative)
            conf_str = SystemConfigService.get_value("INTENT_MIN_CONFIDENCE")
            min_confidence = float(conf_str) if conf_str else cls.MIN_CONFIDENCE

            model = cls.get_model()
            
            # Prediction returns a list of tuples: [(label, confidence), ...]
            predictions = model.predict(message)

            if not predictions:
                logger.debug("[IntentClassifier] No predictions returned")
                return None

            prediction = predictions[0]

            # adaptive-classifier likely returns MultiLabelPrediction or similar which might behave like a tuple
            # or it's a raw tuple.
            if isinstance(prediction, tuple) or isinstance(prediction, list):
                 label = prediction[0]
                 confidence = prediction[1]
            else:
                 # Fallback to attribute access if it changes again
                 label = getattr(prediction, 'label', None)
                 confidence = getattr(prediction, 'confidence', 0.0)

            if confidence >= min_confidence:
                logger.info(f"[IntentClassifier] ⚡ Matched: '{label}' (confidence: {confidence:.2f} >= {min_confidence})")
                return label

            logger.debug(f"[IntentClassifier] Low confidence ({confidence:.2f} < {min_confidence}), fallback to LLM")
            return None

        except Exception as e:
            logger.error(f"[IntentClassifier] Prediction failed: {e}")
            return None

    @classmethod
    def update(cls, text: str, label: str):
        """Allow runtime updates to the classifier (Continuous Learning)."""
        try:
            model = cls.get_model()
            # method is add_examples which takes lists
            model.add_examples([text], [label])
            logger.info(f"[IntentClassifier] Learned new example for '{label}'")
        except Exception as e:
            logger.error(f"[IntentClassifier] Update failed: {e}")

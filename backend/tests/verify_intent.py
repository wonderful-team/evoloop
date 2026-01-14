import logging

from app.core.workflows.intent_classifier import IntentClassifier

# Configure logging
logging.basicConfig(level=logging.INFO, format='%(message)s')
logger = logging.getLogger("VERIFY")

def test_intent(message, expected, threshold=0.65):
    print(f"\n🧪 Testing: '{message}'")

    # 1. Warm-up / Load model
    model = IntentClassifier.get_model()
    try:
        print(f"Memory Stats: {model.get_memory_stats()}")
    except Exception:
        pass

    # 2. Predict
    predictions = model.predict(message)
    if not predictions:
        print(f"   ⚠️  No predictions returned for '{message}'")
        return

    prediction = predictions[0]

    if isinstance(prediction, tuple) or isinstance(prediction, list):
         label = prediction[0]
         conf = prediction[1]
    else:
         label = getattr(prediction, 'label', None)
         conf = getattr(prediction, 'confidence', 0.0)

    # 3. Validation
    if expected is None:
        # Ambiguous case: Success if confidence is low OR no prediction
        success = (conf < threshold)
        expected_str = "None (Low Confidence)"
    else:
        success = (label == expected) and (conf >= threshold)
        expected_str = expected

    icon = "✅" if success else "❌"

    print(f"   Pred: {label} ({conf:.2f}) | Exp: {expected_str} | {icon}")

    if not success:
        if expected is None:
             print(f"   ⚠️  Unexpectedly High Confidence! (Threshold: {threshold})")
        else:
             print(f"   ⚠️  Mismatch or Low Confidence! (Threshold: {threshold})")

if __name__ == "__main__":
    print("🚀 Starting Extended Chinese Intent Verification...")
    print("----------------------------------------")

    test_cases = [
        # Coder
        ("优化这段代码的性能", "coder"),
        ("这个函数报错了", "coder"),
        ("添加一个删除用户的接口", "coder"),
        ("review一下我的代码", "coder"),

        # Documenter
        ("更新一下 API 文档", "documenter"),
        ("把这个项目的架构写成 Wiki", "documenter"),
        ("帮我生成一份 README", "documenter"),

        # Deep Researcher
        ("帮我调研一下最新的 LLM 框架", "deep_researcher"),
        ("分析一下 React 和 Vue 的优缺点", "deep_researcher"),
        ("搜索一下关于 RAG 的最佳实践", "deep_researcher"),

        # Planner
        ("设计一下电商系统的数据库表结构", "planner"),
        ("制定一个下周的开发计划", "planner"),
        ("帮我拆解一下这个任务", "planner"),

        # Requirement Analyst
        ("我想做一个类似 notion 的笔记应用", "requirement_analyst"),
        ("用户说他们需要导出报表的功能", "requirement_analyst"),

        # Ambiguous / Chat (Expect Low Confidence/None)
        ("你好", None),
        ("今天的任务是什么", None),
        ("这就很奇怪了", None)
    ]

    for text, expected in test_cases:
        test_intent(text, expected, threshold=0.35)

    print("\n----------------------------------------")
    print("🏁 Verification Complete.")

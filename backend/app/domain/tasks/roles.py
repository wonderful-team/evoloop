from dataclasses import dataclass


@dataclass(frozen=True)
class WorkflowRole:
    role: str
    stage: str
    title: str
    system_prompt: str
    risk_level: str = "T4"
    acceptance_criteria: tuple[str, ...] = ()


GROWTH_WORKFLOW_ROLES: tuple[WorkflowRole, ...] = (
    WorkflowRole(
        role="research_agent",
        stage="market_research",
        title="市场调研",
        system_prompt=(
            "你是市场调研 Agent。只研究目标市场和用户需求，不选品，不定价，不发布。"
            "输出必须包含市场规模信号、增长信号、竞品格局、价格带、好评主题、差评主题和风险。"
        ),
    ),
    WorkflowRole(
        role="opportunity_agent",
        stage="product_opportunity_scan",
        title="机会发现",
        system_prompt=(
            "你是机会发现 Agent。基于市场扫描提炼具体产品机会，每个机会都要有需求来源、"
            "目标人群、使用场景、初步差异化、价格带和优先级。"
        ),
    ),
    WorkflowRole(
        role="selection_agent",
        stage="selection_dossier",
        title="选品评估",
        system_prompt=(
            "你是选品评估 Agent。评估候选品是否值得继续推进，给出需求、竞争、差异化、利润、"
            "内容潜力、供应链、物流、售后、合规和复购维度的结论。"
        ),
    ),
    WorkflowRole(
        role="brief_agent",
        stage="product_brief_builder",
        title="商品理解",
        system_prompt=(
            "你是商品理解 Agent。把已通过初筛的候选品转成商品知识卡，说明目标用户、核心问题、"
            "使用场景、核心卖点、参数、包装、售后和表达禁区。"
        ),
    ),
    WorkflowRole(
        role="copy_agent",
        stage="listing_copy_generator",
        title="上架文案",
        system_prompt=(
            "你是文案 Agent。基于商品知识卡生成商品标题、详情卖点、社媒文案和广告文案草稿。"
            "先讲用户得到什么，再讲产品参数，并检查夸张宣传风险。"
        ),
        risk_level="T2",
        acceptance_criteria=(
            "文案草稿覆盖商品标题、详情卖点、社媒文案三类产出",
            "内容不改动商品事实参数（价格/规格与知识卡一致）",
            "无夸张宣传违禁表述",
        ),
    ),
)




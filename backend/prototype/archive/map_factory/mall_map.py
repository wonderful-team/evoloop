"""商城 AppMap 最小验证数据(单实体 goods)。

字段对齐草案 §7.7 五层(路径/动作/元素/逻辑/数据)+ §7.9 结构化行(project_id 一等公民)。
来源已实锤(member-center/backend,2026-07-14):
  - 控制器 app/shop/controller/Goods.php: lists:50 / editGoods:430 / editGoodsStock:702 / getGoodsSkuList:760
  - 视图  app/shop/view/goods/edit_goods.html: edit_price:433 / edit_sku_id:429 / js-save:693 / name="price":342
  - 路由  ThinkPHP 约定 module/controller/action -> URL
"""

GOODS_MAP: dict = {
    "project_id": 1,
    "entity": "goods",
    "aliases": ["商品", "铰链", "货品", "goods", "product"],
    "facet": "both",  # ui(界面切面) + data(数据切面)
    # ① 路径 paths
    "routes": [
        {"name": "goods_list", "url": "/shop/goods/lists", "method": "GET", "source_action": "lists"},
        {"name": "goods_edit", "url": "/shop/goods/editgoods", "method": "POST", "source_action": "editGoods"},
    ],
    # ② 动作 actions(已标 kind/risk/规则 = §7.8 阶段 A+B 产出)
    "actions": [
        {
            "name": "lists", "kind": "read", "risk_tier": "ui",
            "touches_tables": ["goods", "sku"],
            "business_rule": "商品列表, 可按名称/货号筛选",
            "controller": "Goods.php", "line": 50,
        },
        {
            "name": "getGoodsSkuList", "kind": "read", "risk_tier": "data",
            "touches_tables": ["sku"],
            "business_rule": "取商品 SKU 列表; 价格挂在 SKU 上(price 取第一个 SKU)",
            "controller": "Goods.php", "line": 760,
        },
        {
            "name": "editGoods", "kind": "write", "risk_tier": "money",
            "touches_tables": ["sku"], "set_fields": ["price"], "pk": "sku_id",
            "business_rule": "改价 = 改第一个 SKU 的 price; 触 price 字段即 money",
            "controller": "Goods.php", "line": 430,
        },
    ],
    # ③ 元素 elements
    "elements": [
        {"name": "edit_price", "page": "edit_goods.html", "line": 433, "binds": "SKU 价格输入框"},
        {"name": "edit_sku_id", "page": "edit_goods.html", "line": 429, "binds": "SKU id"},
        {"name": "js-save", "page": "edit_goods.html", "line": 693, "binds": "保存按钮"},
    ],
    # ⑤ 数据 data
    "db_tables": [
        {"table": "sku", "pk": "sku_id", "cols": ["sku_id", "goods_id", "price", "stock"]},
        {"table": "goods", "pk": "goods_id", "cols": ["goods_id", "goods_name"]},
    ],
    "content_hash": "goods-v1",
    "map_version": 1,
}

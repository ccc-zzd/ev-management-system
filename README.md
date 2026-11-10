# 新能源汽车综合管理与推荐系统

基于 Flask + MySQL 的新能源汽车信息管理与智能推荐平台，支持车型浏览与筛选、多维度参数对比、评分统计可视化、智能推荐、预约试驾、订单与维修服务，以及后台数据管理。

## 技术栈

| 层次 | 技术 |
|---|---|
| 后端 | Python 3.10+、Flask 3、PyMySQL |
| 数据库 | MySQL 8（utf8mb4） |
| 数据处理 | pandas、csv、Pillow |
| 前端 | Jinja2 模板、Bootstrap 5、ECharts |
| 静态资源 | Bootstrap / Bootstrap Icons / ECharts 均已本地化到 `static/vendor`，离线可用 |

## 功能模块

**用户端**

- 首页：平台概览、数据统计卡片、AI 智能选车输入框、热门车型推荐
- 车型列表：按品牌、价格区间、能源类型、续航等条件筛选与分页
- 车型详情：基础参数、性能指标、多维度评分雷达图、车主评价、收藏
- 智能推荐：`/api/smart_recommend` 按预算、续航、品牌、偏好加权打分；`/api/nl_recommend` 解析自然语言条件（如「20万预算续航500km比亚迪性价比」）
- 评分排行：`/api/rank` 输出综合评分榜
- 数据统计：品牌分布、价格分布、续航分布、车型结构、品牌评分对比等 ECharts 图表
- 个人中心：注册登录、资料与密码修改、收藏、预约试驾、订单、维修工单

**管理端**（`/admin`，默认账号 `admin / admin123`）

- 车型增删改查、CSV 批量导入
- 试驾预约确认 / 完成、订单交付、维修工单处理、评价审核

## 目录结构

```
ev-management-system/
├── app.py                 # Flask 主应用：页面路由 + REST API
├── init_db.py             # 建库建表、导入 CSV、初始化管理员
├── db_config.py           # 数据库连接与数据目录配置
├── requirements.txt
├── Data/                  # 数据集目录（CSV 不入库，见下方说明）
├── static/
│   ├── cars/              # 车型图片（已压缩）
│   └── vendor/            # 本地化的 Bootstrap / Icons / ECharts
└── templates/             # 15 个 Jinja2 页面模板
```

## 快速开始

1. 安装依赖

```bash
python -m venv .venv
.venv\Scripts\activate        # Windows
pip install -r requirements.txt
```

2. 配置数据库

修改 `db_config.py` 中的 `DB_CONFIG`（默认 `127.0.0.1:3306`，用户 `root`，密码 `123456`，库名 `ev_management`），按本机环境调整。

3. 准备数据

将以下三份 CSV 放入 `Data/` 目录（文件名需一致）：

| 文件 | 说明 |
|---|---|
| `车辆基础信息.csv` | 车型基础参数 |
| `车型维度评分.csv` | 各维度评分 |
| `用户评论数据.csv` | 用户评论 |

> 数据集体积较大（评论表约 120 MB），且含用户评论内容，因此不纳入版本库。

4. 初始化数据库并导入数据

```bash
python init_db.py
```

脚本会自动创建数据库与数据表、导入三份 CSV，并写入默认管理员账号。

5. 启动服务

```bash
python app.py
```

浏览器访问 `http://127.0.0.1:5000`。

## 主要接口

| 接口 | 方法 | 说明 |
|---|---|---|
| `/api/vehicles` | GET | 车型列表，支持品牌、价格、续航、关键词、分页 |
| `/api/car_detail` | GET | 车型详情与评分、评论 |
| `/api/smart_recommend` | GET | 条件加权推荐 |
| `/api/nl_recommend` | GET | 自然语言条件解析推荐 |
| `/api/rank` | GET | 综合评分排行 |
| `/api/stats/*` | GET | 品牌、价格、续航、类型、评分等统计聚合 |
| `/api/favorite` | POST/DELETE | 收藏管理 |
| `/api/test_drive` | POST | 试驾预约 |
| `/api/order` | POST | 下单与支付 |
| `/api/repair` | POST | 维修预约 |
| `/api/import` | POST | 管理端 CSV 导入 |

## 说明

- `app.secret_key` 与数据库口令为本地演示默认值，部署到公网前请改为环境变量或独立配置文件。
- 车型图片仅用于教学演示，版权归原作者所有。

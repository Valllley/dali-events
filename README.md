# 🦋 大理活动日历 | Dali Events Calendar

大理旅居人群的活动信息聚合站。自动采集多源信息，结构化展示市集、音乐、民俗、讲座等活动。

## 在线访问

部署到 Vercel 后即可在线访问，支持手机端浏览。

## 项目结构

```
dali-events/
├── index.html                  # 前端单页应用（可直接打开）
├── data/
│   └── events.json             # 结构化活动数据
├── scraper/
│   ├── scrape.py               # 数据采集脚本
│   └── requirements.txt        # Python依赖
├── .github/
│   └── workflows/
│       └── update.yml          # GitHub Actions自动更新
└── README.md
```

## 快速开始

### 1. 本地预览

直接打开 `index.html` 即可查看活动列表（已内置数据）。

### 2. 数据采集

```bash
# 安装依赖
cd scraper
pip install -r requirements.txt

# 设置API Key（用于LLM结构化提取）
export OPENAI_API_KEY="sk-..."

# 全量抓取
python scrape.py

# 只搜索不提取（省LLM费用）
python scrape.py --dry-run

# 只抓微信公众号
python scrape.py --source wechat
```

### 3. 自动更新（GitHub Actions）

1. Fork 本仓库
2. 在仓库 Settings → Secrets 中添加 `OPENAI_API_KEY`
3. 每天8:00自动执行采集，有新数据自动commit推送

### 4. 部署到 Vercel

1. 将仓库推送到 GitHub
2. 在 Vercel 导入该仓库
3. 构建设置：Framework Preset 选 "Other"，Output Directory 设为 `.`
4. 部署完成后获得在线地址

## 数据源

| 来源 | 类型 | 更新频率 | 采集难度 |
|------|------|----------|----------|
| 微信公众号（大理旅游/大理好在/大理融媒） | 公众号 | 1-3天 | ⭐⭐⭐⭐ |
| 小红书（市集/活动帖） | 社交媒体 | 实时 | ⭐⭐⭐⭐⭐ |
| 大理文旅网 | 政务网站 | 1-2周 | ⭐⭐ |
| 携程/马蜂窝 | 旅游平台 | 1-3天 | ⭐⭐⭐ |
| 抖音/头条号 | 短视频 | 实时 | ⭐⭐⭐⭐ |

## 数据格式

每个活动包含以下字段：

```json
{
  "id": "butterfly-festival-2026",
  "title": "🦋 蝴蝶会 · 白族情人节",
  "date_start": "2026-05-31",
  "date_end": "2026-05-31",
  "time": "全天",
  "location": "蝴蝶泉景区",
  "location_map": "大理市蝴蝶泉景区",
  "price": "8元(居民/学生证/居住证) / 正常购票",
  "category": "民俗节庆",
  "tags": ["民俗", "非遗", "音乐", "市集", "年度重磅"],
  "description": "延续几百年的白族「情人节」...",
  "highlights": ["非遗洞经古乐 × 现代音乐双舞台", ...],
  "tips": "当天人流量暴增，建议9点前入园",
  "source_name": "大理融媒",
  "source_url": "https://..."
}
```

## 功能规划

- [x] 基础前端展示（日历+列表）
- [x] 分类筛选
- [x] 活动详情弹窗
- [x] 移动端适配
- [x] Python采集脚本
- [x] GitHub Actions自动更新
- [ ] 微信公众号推送（每日早报）
- [ ] 小红书数据源接入
- [ ] PWA离线支持
- [ ] 活动提醒功能
- [ ] UGC投稿（社区提交活动）
- [ ] 高德地图定位集成
- [ ] RSS输出

## 技术栈

- **前端**: HTML + Tailwind CSS + Vanilla JS（零构建，零依赖）
- **采集**: Python + requests + OpenAI API
- **部署**: Vercel（静态站点）
- **自动更新**: GitHub Actions

## 许可

MIT

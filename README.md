# 每日研究简报 (daily-digest)

每天定时给指定邮箱发一封邮件，包含两部分：

1. **新文献**：从政治学顶级期刊抓取最近的新文章（OpenAlex），按你的研究兴趣筛选，并从摘要中提炼核心问题 / 发现 / 方法。
2. **地区政治新闻**：分别收集韩国、马来西亚、菲律宾、台湾当天的政治新闻（Google News），各自生成一段综述。

## 工作原理

```
main.py
 ├─ src/literature.py   OpenAlex 抓取 → 关键词初筛 → Claude 打分 + 提炼
 ├─ src/news.py         Google News RSS 抓取 → Claude 综述
 ├─ src/digest.py       组装 HTML 邮件
 └─ src/mailer.py       SMTP 发送
```

文献用 OpenAlex（免费、无需 key）。筛选和总结用 Anthropic API（按量计费，和 Claude 订阅分开；一天大约几分钱）。**没有 API key 也能跑**：文献退化为关键词排序、新闻只列标题。

## 一次性准备

1. **改配置**：把 `config.example.yaml` 复制成 `config.yaml`，编辑期刊列表、`interest_profile`（研究兴趣，我预填了一份草稿，请按自己的方向改）、关键词、四个地区、以及邮箱字段（`from` / `to` / SMTP 主机）。

2. **邮箱应用密码**：如果用 Gmail，需要开启两步验证后生成一个「应用专用密码」（16 位），用它而不是登录密码。其他邮箱同理，找 SMTP 设置和应用密码。

3. **三个密钥**（不要写进配置文件，走环境变量）：
   - `ANTHROPIC_API_KEY`（可选，没有就走降级模式）
   - `SMTP_USERNAME`（一般就是发件邮箱）
   - `SMTP_PASSWORD`（上一步的应用密码）

## 本地试跑

```bash
pip install -r requirements.txt
export ANTHROPIC_API_KEY=sk-ant-...
export SMTP_USERNAME=you@gmail.com
export SMTP_PASSWORD=your-app-password
python main.py
```

先跑一次确认邮件能收到、内容合适，再上定时。

## 定时运行（推荐 GitHub Actions）

好处：免费、你的电脑不用开机、密钥有安全存放处。

1. 把整个文件夹推到一个 GitHub 私有仓库。
2. 仓库 **Settings → Secrets and variables → Actions** 里加上面三个密钥。
3. 定时时间在 `.github/workflows/daily.yml` 的 `cron` 里改。cron 用 **UTC**：你在首尔（UTC+9），想早上 8 点收信就写 `0 23 * * *`（前一天 23:00 UTC）。
4. 到 **Actions** 标签页可以手动点一次 `Run workflow` 测试。

`seen.json` 记录已发过的文献 DOI，避免重复；workflow 每次会把它提交回仓库。

### 或者：本地 cron / 任务计划程序

`config.yaml` 就位、密钥写进你的 shell 配置后，加一条 crontab（需要电脑在设定时间开着）：

```
0 8 * * *  cd /path/to/daily-digest && /usr/bin/python3 main.py >> run.log 2>&1
```

## 常见调整

- **期刊**：直接改 `journals` 列表，用期刊全名即可，脚本会自动解析成 OpenAlex 内部 ID（首次运行时解析并缓存到 `sources.json`；若某个名字没解析成功会打印警告，换个更规范的全名）。
- **筛得太宽 / 太窄**：先调 `keywords`（初筛），再调 `interest_profile`（交给模型的判断依据）。
- **新闻语言**：`news_language` 改成 `English` 就出英文综述。想加地区就往 `regions` 里加一项，`hl/gl/ceid` 是 Google News 的地区语言参数。
- **文献质量不够**：把 `model` 换成更强的模型（成本略升）。
- **拿不到摘要**：OpenAlex 个别新文章摘要可能缺失，这属正常，等它补数据；也可以把 `lookback_days` 调大一点。

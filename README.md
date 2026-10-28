# 每日科学简报：Calibre + RSS

每期一本 EPUB，**7 篇**：前沿研究 3 篇（力学 / 机械 / 航空 / 超结构 / 智能结构 / 弹性波调控 / 非线性，英文文献为主）+ 科普 1 篇 + 物理及其它更广 1 篇 + 时事 2 篇。

两种跑法，出一样的书：

| 跑法 | 怎么触发 | 适合 |
| --- | --- | --- |
| **本地双击**（推荐先用这条） | 双击 `daily-brief.bat`，或用 `schtasks` 每天定时叫它一次 | 你已经有代理、想马上看到书、不想把源清单放到 GitHub |
| **云端 GitHub Actions** | 定时（默认每天 08:00 北京时间）或 Actions 页面点 Run workflow | 电脑不用常开，海外源直接可达，配好 Secrets 还能自动发邮件 / 推 Kindle |

## 文件结构

```
daily-brief.bat                        本地一键出书（双击）
recipes/daily-science-brief.recipe     配额 + 订阅源 + 选题关键词（唯一配置出处）
scripts/pick_articles.py               抓 RSS、按类别配额挑文章 → build/picked.json
scripts/build_brief.py                 选材 → 调 ebook-convert 排版 → 清理旧书
scripts/recipe_config.py               用 AST 从配方里读配置（普通 python import 不了 calibre 包）
scripts/check_feeds.py                 源可达性 + 停更检测
scripts/send_email.py                  SMTP 发信（纯标准库，默认不启用）
.github/workflows/daily-brief.yml      云端流水线：装 Calibre → 自检源 → 出书 → 归档 / 发邮件
out/                                   本地生成的书（不入库）；briefs/ 是云端归档
```

## 本地跑（双击 bat，或命令行）

前提：装好 [Calibre](https://calibre-ebook.com/download_windows)（本机在 `D:\Program\Calibre2`）和 Python 3。

双击 `daily-brief.bat` → 抓源、选材、排版 → 用默认阅读器打开 `out\每日科学简报-2026-10-28.epub`。
命令行等价：

```bash
python scripts/build_brief.py            # 出书
python scripts/pick_articles.py --print-only   # 只看本期会选哪 7 篇，不出书
python scripts/build_brief.py --skip-pick      # 沿用上次选材，只重排一遍（调版式时用）
python scripts/build_brief.py --days 7         # 临时把新鲜度窗口收紧到 7 天
```

`ebook-convert` 不在默认位置时设 `EBOOK_CONVERT` 指向它。`out/` 里默认只留最近 14 本，`--keep` 改。

### 让它每天自动跑（还是本地，不用云）

`bat` 双击和定时是两回事——定时交给 Windows 自带的任务程序，一条命令：

```bat
schtasks /Create /SC DAILY /ST 08:00 /TN "每日科学简报" ^
  /TR "'D:\Personal\calibre-daily-brief\daily-brief.bat'" /F
```

删掉：`schtasks /Delete /TN "每日科学简报" /F`。想开机就跑就 `/SC ONSTART`；先看效果可以去掉 `/F` 再手动 `schtasks /Run /TN "每日科学简报"`。

代价是**电脑得开着**：笔记本合盖、关机的那些天就没有这期，也不会补跑。

### 代理

配方里的 37 个源全部是**本机不开代理时实测可达**的，所以默认不用配代理。想收 Guardian / BBC / Google News，把 `bat` 里这两行注释去掉（端口改成自己的），并取消配方里对应源的注释：

```bat
set HTTP_PROXY=http://127.0.0.1:7890
set HTTPS_PROXY=http://127.0.0.1:7890
```

## 本地和云端差在哪

正文、版式、选题规则**完全一样**（两边都走 `build_brief.py`）。真正的区别只有这些：

| | 本地 bat | 云端 Actions |
| --- | --- | --- |
| 电脑要不要开着 | 要（定时也得开机） | 不要 |
| **网络可达性** | 国内直连：Google/Guardian/BBC 被墙，需代理 | 海外 runner：这些通；但 `rsshub.app` 等对云端 IP 限流 403 |
| 邮件 / 推 Kindle | 自己 `python scripts/send_email.py out/xxx.epub`，密码放环境变量 | 配好 Secrets 自动多发一步 |
| 历史归档 | 本地 `out/`，只留 14 本 | 仓库 `briefs/` + Actions 产物（30 天） |
| 跨天去重 | 本地 `state/seen.json`，天天有效 | 每次运行是干净环境，`state/` 不入库 → **只在同一天内去重**，明天可能重推同一篇 |
| 成本 | 电费 | 私有仓库每月 2000 分钟免费额度，本任务约 1–2 分钟 |
| 隐私 | 全在本地 | 仓库 Actions 日志里有本期标题列表 |

最后一行值得展开：**云端要真正做到"每天不重样"，得把 `state/seen.json` 一起提交回仓库**（归档那步顺手 `git add state`），否则去重历史每次运行都清零。这是本地方案唯一实打实比云端好的地方。

## 每期收几篇、怎么收

配额、章节名、新鲜度窗口都在配方顶部：

```python
QUOTA = {'frontier': 3, 'popular': 1, 'broad': 1, 'current': 2}
FRESH_DAYS = {'frontier': 45, 'popular': 30, 'broad': 21, 'current': 3}
```

选一篇的流程（`scripts/pick_articles.py`）：

1. 并发抓 37 个源，解析 RSS/Atom，按类别的 `FRESH_DAYS` 丢掉过期条目；
2. `TOPIC_KEYWORDS` 打分：命中**标题**的 strong 词 3 分、命中**摘要** 1 分，weak 词命中标题 1 分（`metamaterial`、`phononic`、`elastic wave`、`band gap`、`piezoelectric`、`nonlinear vibration`、`topological mechanic`… 连中文词一起）；
3. 前沿一组只留得分 > 0 的，按分数排；科普 / 物理 / 时事按最新排；
4. `EXCLUDE_TITLE` 干掉 "The Download"、"周报"、"盘点" 这类合集，别浪费唯一的科普格子；
5. **同组轮流取，尽量不集中在同一本期刊**；前沿只有 3 格，`pick_diverse` 保证 3 篇来自 3 个源；
6. 跨天去重：`state/seen.json` 里已经推过的先跳过；跳过之后凑不满配额，再允许重复（宁可重一篇也不要空章节）；
7. 写 `build/picked.json`，配方 `parse_index()` 读它，Calibre 只负责排版打包。

两个绕不开的实现原因：

- **Calibre 做不到按类别配额**。它只有 `max_articles_per_feed` 一个**全局**开关，所以配额必须自己写（第 2 步），Calibre 收的是已经选好的 7 条。
- **正文用的是 RSS 自带的摘要，不去抓网页**（配方里 `use_embedded_content = True`）。期刊 RSS 给的就是完整摘要，够读，而且不踩出版社反爬、本地一秒出书。想读全文改成 `False`，代价是慢、容易被 403，而且全文只适合你自己看，别把整本书转发出去。

## 改订阅源

改配方里的 `FEED_GROUPS`，一行一个源；想停用就在前面加 `#`。加完先验：

```bash
python scripts/check_feeds.py                  # 可达性 + 最新一条是几天前的
python scripts/pick_articles.py --print-only   # 看看新源有没有真的选出东西
```

`check_feeds.py` 会报**停更**，光看能不能返回 200 是不够的——这次就抓出几个"能返回上百条、但快照停在几年前的"死源：

| 情况 | 源 |
| --- | --- |
| 200 + 最新 0–2 天内 | 全部 37 个现役源（`check_feeds.py` 实测 37/37 OK） |
| **返回 200、上百条，但停更**（已剔除） | 人民网 时政/国际（停在 2025-06-05）、新浪科技滚动（停在 2018-09-23） |
| 404 / 500 / 非 RSS（已剔除） | APS PRL、Nature Communications、Scientific American、Phys.org 子频道、光明网、环球、观察者网、CSDN、ChinaDaily、联合早报（返回 HTML）、36氪 / 机器之心 / cnBeta（返回 HTML）、`rsshub.app` 系（本机连不上） |
| 需要代理才通 | Guardian、BBC、Google News 中文（配方里注释好了） |

一个必须知道的现实：**本机探测和 runner 探测会给出不同答案**。国内直连时 Google/Guardian 整批失败，海外 runner 反过来会被 `rsshub.app` 限流。所以换源之后，本地跑一遍 `check_feeds.py`，云端再看 Actions Summary 里那张表。

## 打开邮件推送（云端可选）

仓库 **Settings → Secrets and variables → Actions → New repository secret**：

| Secret | 例子 |
| --- | --- |
| `SMTP_HOST` | `smtp.qq.com` |
| `SMTP_PORT` | `465`（SSL）或 `587`（STARTTLS） |
| `SMTP_USER` | `you@qq.com` |
| `SMTP_PASS` | **授权码 / 应用专用密码**，不是网页登录密码 |
| `MAIL_TO` | `reader@example.com`，多个用逗号分隔 |
| `MAIL_FROM` | 可选，多数邮箱必须等于 `SMTP_USER` |

授权码位置：QQ 邮箱 设置 → 账户 → POP3/IMAP/SMTP 服务里「生成授权码」；163/126 在 设置 → POP3/SMTP/IMAP 开客户端授权密码；Gmail 先开两步验证再生成 App Password；Outlook.com 现在也要求应用密码。

本地发同一本书：

```bash
SMTP_HOST=smtp.qq.com SMTP_PORT=465 SMTP_USER=you@qq.com SMTP_PASS=授权码 \
MAIL_TO=reader@example.com python3 scripts/send_email.py out/每日科学简报-2026-10-28.epub
```

**发给 Kindle**：`MAIL_TO` 换成你的 `xxx@kindle.com`（国行 `@kindle.cn`），并先在亚马逊 **Manage Your Content and Devices → Preferences → Personal Document Settings** 把发件邮箱加进 Approved list，否则静默退信。现在一本约 0.2 MB（7 篇 + 摘要 + 3 张图），离 10 MB 限制很远。

## 云端跑起来（约 5 分钟）

1. GitHub 新建仓库（私有也行）。
2. 上传全部文件（含 `.github/`），提交到默认分支。
3. **Settings → Actions → General → Workflow permissions** 选 **Read and write permissions**，否则归档那步 `git push` 会 403。
4. **Actions → 每日科学简报 → Run workflow** 手动跑一次。
5. 成果在三个地方：这次运行的 Summary（源自检表 + 本期目录和大小）、页面底部 **Artifacts**、仓库 `briefs/` 的新提交。

只有 `schedule` 会跑在默认分支上；`workflow_dispatch` 和 `push` 可以跑在任意分支，方便先试。

### cron 用 UTC，比北京时间早 8 小时

| 想要的北京时间 | cron |
| --- | --- |
| 08:00（当前默认） | `0 0 * * *` |
| 07:30 | `30 23 * * *`（前一天 UTC） |
| 12:00 | `0 4 * * *` |
| 08:00 + 20:00 | `0 0,12 * * *` |
| 工作日 09:00 | `0 1 * * 1-5` |

GitHub 高峰期定时可能延迟十几分钟甚至偶尔跳过，是平台行为。

## 故障排查

| 现象 | 原因 | 处理 |
| --- | --- | --- |
| `没找到 ebook-convert` | 没装 Calibre，或装在非默认位置 | 装 [Calibre](https://calibre-ebook.com/download_windows)，或设 `EBOOK_CONVERT` 指向 exe |
| `一篇都没选到` | 当前网络一个源都没连上，或全部超出新鲜度窗口 | 看上面每个源的抓取日志；`--days 45` 放宽窗口 |
| 某段是 `0/3`、`0/2` | 这一段所有源都挂了，或全被去重/停更挡掉 | `python scripts/pick_articles.py --no-history --print-only` 看是哪一步空的 |
| 前沿一篇只有标题、没摘要 | Elsevier 的 RSS 不提供摘要（`OpenAlex` 也常缺）；已在第 5 步优先选自带摘要的源，偶尔仍会补位 | 想要更长的，把 `arXiv` / `Smart Mater. Struct.` 的权重词再收紧 |
| 时事 0 篇 | 国内活着的 RSS 真不多，人民网/新浪那批是死快照 | 已换成中新网 / 界面 / Solidot / 爱范儿；要外媒就开代理 |
| 中文 echo 乱码（bat 窗口） | 控制台代码页 | bat 里已经 `chcp 65001`；还乱就是终端不支持 UTF-8，不影响出书 |
| 装 Calibre 那一步超时（云端） | 下载 ~100MB 二进制偶发慢 | 重跑；或给仓库加 Actions 缓存 |
| 整本书几乎是空的 | 全部源在该位置不可达 | 看自检表，先减到 2–3 个源验证链路 |
| `git push` 403（云端） | Workflow permissions 还是只读 | 改成 Read and write |
| SMTP 认证失败 | 用了网页登录密码 | 换成授权码 / App Password |
| 云端每天都推同样的文章 | 干净环境里 `state/seen.json` 每次清零 | 把 `state/` 也提交回仓库（见上表） |

## 关于这份实现的可靠性

已经实测过的：

- **本地整条链路真跑通了**：Calibre 9.17（`D:\Program\Calibre2`）实跑出 `out/每日科学简报-2026-10-28.epub`，0.18 MB，4 个章节、7 篇文章、3 张图，每篇正文 300–5000 字符。
- **配方字段**：`language`、`publication_type`、`timefmt`、`max_articles_per_feed`、`oldest_article`、`remove_empty_feeds`、`ignore_duplicate_articles`、`use_embedded_content`、`compress_news_images*`、`scale_news_images`、`conversion_options`、`feeds`，以及 `parse_index(self)` 返回 `[(章节, [文章 dict])]` 的写法，都对照 Calibre 9.17 的 `calibre.web.feeds.news` 源码确认过（本机 `calibre-debug` 查签名 + 官方 `news.py`）。旧教程里的 `language_code`、`timeofprint` 现在已不是有效字段。
- **订阅源**：37 个现役源本机 `check_feeds.py` 实测 37/37 可用且最新条目在 0–2 天内。探测过程中剔掉了上面那张表里的死源。
- **脚本**：`scripts/*.py` 通过 `python -m py_compile`，`pick_articles.py` / `build_brief.py` / `check_feeds.py` 都真实跑过（含并发抓取、失败重试、OpenAlex 摘要补全、跨天去重）。

还没验证的：

- **这条 workflow 没在真实 GitHub 仓库上跑过**（要有你的仓库才能触发）。本地跑的是同一个 `build_brief.py`，所以风险集中在云端装 Calibre 那步，不在脚本逻辑。
- **OpenAlex 补摘要的覆盖率**：Elsevier 那批期刊经常没有（`api.openalex.org` 可达，命中率体感 1/3 左右），所以逻辑是"补不到就退回标题"，不硬求。
- 云端 runner 侧的源可达性（跟本机结论常常相反，跑完看 Summary）。

## 可选扩展

- **跨天去重上云**：归档那步顺手 `git add state/`，让云端也保住历史。
- **拆成两本**：复制配方改 `title` 和 `QUOTA`，科学 / 时事各一本。
- **输出 MOBI/AZW3**：`ebook-convert 输入.epub 输出.azw3`，或加 `--output-profile` 适配设备。
- **阅读器直接订阅**：Calibre-Web / OPDS 同步 `out/`，省掉邮件。
- **中文导语**：现在标题是英文原样。要每篇配一句中文摘要，得接翻译，属于另一个改动。

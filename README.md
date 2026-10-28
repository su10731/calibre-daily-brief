# 科学简报：Calibre + RSS，一个大类一本书

按大类拆成 9 本书，根目录一个 `.bat` 对应一本，想看哪本点哪本：

| bat | 书 | 篇数 | 内容 | 要不要代理 |
| --- | --- | --- | --- | --- |
| `0-每日简报-7篇.bat` | 每日科学简报 | 3+1+1+2 | 力学3 + 科普1 + 物理1 + 国内时事2 | 不用 |
| `1-科学前沿-3篇.bat` | 科学前沿速递 | 3 | 力学 / 机械 / 航空 / 超结构 / 智能结构 / 弹性波调控 / 非线性（英文期刊 + arXiv） | 不用 |
| `2-材料与制造-2篇.bat` | 材料与先进制造 | 2 | 复材 / 碳 / 增材制造 / Nature Materials | 不用 |
| `3-物理速递-2篇.bat` | 物理速递 | 2 | Phys.org、Nature/Science 新闻、Phys. Lett. A | 不用 |
| `4-科普拓展-2篇.bat` | 科普知识拓展 | 2 | Quanta、MIT TR、Physics World、New Scientist | 不用 |
| `5-科技AI-2篇.bat` | 科技与AI | 2 | Hacker News、Ars Technica、InfoQ 中文、开源中国 | 不用 |
| `6-时事国内-2篇.bat` | 时事国内 | 2 | 中新网、界面、Solidot、科学网、爱范儿 | 不用 |
| `7-时事国际-2篇.bat` | 时事国际 | 2 | Guardian、BBC、NYT、Economist、FT | **要** |
| `8-深度长文-2篇.bat` | 深度长文 | 2 | Aeon、The Atlantic | **要** |

0–6 本在国内直连就能出（每本的源都是 2026-10-28 本机实测过的）。7、8 两本的源在国内必挂，所以它们**同时有本地和云端两个入口**：本地那个 bat 先探本机代理端口再抓，云端 runner 在海外不需要代理。

## 文件结构

```
0-*.bat ~ 8-*.bat                      本地一键出书，一本一个（双击）
recipes/daily-science-brief.recipe     大类、源、配额、关键词（唯一配置出处）
scripts/build_brief.py                 入口：选材 → 调 ebook-convert → 打印目录
scripts/pick_articles.py               抓 RSS、按大类配额挑文章 → build/picked-<书>.json
scripts/recipe_config.py               用 AST 从配方里读配置（普通 python import 不了 calibre 包）
scripts/check_feeds.py                 源可达性 + 停更检测
scripts/check_workflow.py              改 workflow 后用：YAML 结构 + 每个 bash 块 bash -n
scripts/send_email.py                  SMTP 发信（纯标准库，默认不启用）
.github/workflows/daily-brief.yml      云端流水线：装 Calibre → 自检源 → 逐本出书 → 归档 / 发邮件
out/                                   本地生成的书（不入库）；briefs/ 是云端归档
state/seen.json                        已推过的文章，用来做同日 / 跨天去重
```

## 本地跑

前提：装好 [Calibre](https://calibre-ebook.com/download_windows)（本机在 `D:\Program\Calibre2`）和 Python 3。

双击任一 `.bat` → 抓源、选材、排版 → 用默认阅读器打开 `out\<书名>-<日期-时分秒>.epub`。命令行等价：

```bash
python scripts/build_brief.py --list-books            # 有哪些书、各几篇
python scripts/build_brief.py --book science --open   # 出"科学前沿"这本并打开
python scripts/pick_articles.py --book tech --print-only   # 只看会选哪几篇，不出书
python scripts/build_brief.py --book daily --skip-pick     # 沿用上次选材，只重排（调版式用）
python scripts/build_brief.py --book science --days 7      # 临时收紧新鲜度窗口
```

`ebook-convert` 不在默认位置时设 `EBOOK_CONVERT` 指向它。`out/` 里每本书各留最近 14 份（`--keep` 改），只删同名书的旧文件，不会误删别的大类。

### 同一天可以反复点

两条都实测过：

- **不覆盖**：文件名带 `YYYY-MM-DD-HHMMSS`，点一次多一份。
- **不重复**：每次选中的文章立刻记进 `state/seen.json`（URL 和规范化标题各记一条），下一次自动换新东西。连点两次 `1-科学前沿-3篇.bat` 实测拿到两组完全不同的文章。
  只有当某个大类去重后凑不满配额才允许重复——宁可重一篇也不留空章节。
  想每次都从最大候选池里选，加 `--no-history`（`pick_articles.py`）或删掉 `state/seen.json`。

### 让它每天自动跑（还是本地，不用云）

双击和定时是两回事，定时交给 Windows 自带的任务程序：

```bat
schtasks /Create /SC DAILY /ST 08:00 /TN "科学简报-前沿" ^
  /TR "'D:\Personal\calibre-daily-brief\1-科学前沿-3篇.bat'" /F
```

哪本想要自动就给它建一个任务，名字各起各的。删掉：`schtasks /Delete /TN "科学简报-前沿" /F`；先试跑：`schtasks /Run /TN "科学简报-前沿"`。

代价是**电脑得开着**：合盖、关机的那些天没有这期，也不会补跑。

### 代理

`7-*.bat` 和 `8-*.bat` 需要代理。`build_brief.py` 先探本机 7890 / 7897 / 10808 / 10809 / 8118 / 33210 / 12781 这些常见端口，探到就给这一个子进程设上 `HTTP_PROXY`、`HTTPS_PROXY`（不动你的系统设置）；探不到就打印一行提示然后照常出书——这一本会是空的或半本。

实测提醒：本机 7897 是开着的、也确实被探到了，但同一条 Guardian 请求**十几分钟内先成功后失败**（`SSL: UNEXPECTED_EOF_WHILE_READING`），换 `build_opener`、换 `urlopen`、串行、并发都失败。问题在代理节点，不在这些脚本。所以国外那两本交给云端更省事；要用本地这条，先确认代理节点能出这些站。不想自动走代理就加 `--no-proxy`。

## 为什么只有标题和摘要（实测）

结论：**不是"被反爬才只剩摘要"——摘要本来就是 RSS 给的全部；正文页另有一层，两家还不一样。**

2026-10-28 在本机直接探文章页（不开代理）：

| 地址 | 结果 | 说明 |
| --- | --- | --- |
| `rss.sciencedirect.com`（Elsevier 期刊 RSS） | 200，但条目里只有标题 / 链接 / `Publication date` | 摘要压根不在 RSS 里；日期靠脚本从描述文本里解析 |
| `www.sciencedirect.com/science/article/pii/...` | **403 Forbidden** | 真反爬，`use_embedded_content = False` 也抓不到 |
| `www.science.org/doi/...` | **403 Forbidden** | 同上 |
| `www.nature.com/articles/...` | 404（用的是测试编号，说明**没被拦**） | 拦你的是付费墙不是反爬；订阅者在 Calibre 里也得登录才有全文 |
| `iopscience.iop.org/article/...` | 200，去标签约 1.2 万字符 | 公开的是摘要页；它的 RSS 同样带完整摘要 |
| `arxiv.org/abs/...` | 200，`meta.description` 就是整段摘要 | 预印本没有付费墙，摘要本身就是全文的浓缩 |

所以配方里 `use_embedded_content = True`：只用源自带的摘要 + 原文链接，不抓网页。三个好处——碰不到出版社的反爬、本地一秒出书、成品里只有摘要和链接（这类摘要本来就是出版社通过 feed 面向订阅者发布的，适合个人订阅阅读；整本书别对外转发）。

要读全文就把 `use_embedded_content` 改成 `False`：只有 IOP、arXiv、Quanta 这类不反爬的站能取到正文，Elsevier / Science 会白等 60 秒超时。

对只有标题的那几篇还有一层补救：选中文章后正文短于 260 字符的，去 OpenAlex 元数据里捞一次摘要（`--no-enrich` 可关）。Elsevier 那批经常没有，实测命中率约三分之一，补不到就退回标题。

## 改大类、改源、改配额

都在 `recipes/daily-science-brief.recipe` 顶部：

```python
QUOTA       = {'science': 3, 'materials': 2, ...}    # 单独出这个大类的书默认几篇
FRESH_DAYS  = {'science': 45, 'current_cn': 2, ...}  # 超过这么多天的文章不要
BOOKS       = {'daily': ('每日科学简报', [('science', 3), ('popular', 1), ...]), ...}
FEED_GROUPS = {'science': [('JMPS 机械物理固体', 'https://rss.sciencedirect.com/...'), ...], ...}
```

`BOOKS` 里 `(大类, None)` 表示用 `QUOTA` 的默认篇数；加一行 `BOOKS` 就等于多一本书，再照着复制一个 `.bat`（bat 之间只有 `--book` 参数不同）。

一篇是怎么被选中的（`scripts/pick_articles.py`）：抓该类所有源 → 按 `FRESH_DAYS` 丢旧的 → `TOPIC_KEYWORDS` 打分（命中标题 3 分、命中摘要 1 分；`metamaterial`、`phononic`、`elastic wave`、`band gap`、`piezoelectric`、`nonlinear vibration`、`topological mechanic` 这类 strong 词，中文等价词也在）→ `SCORED` 那些大类按分数排、其余按时间排 → `EXCLUDE_TITLE` 干掉"周报 / 盘点 / The Download"这类合集 → 同类内轮流取源，避免三篇同一本期刊 → 候选够用时只收带正文摘要的 → 去重 → 补 OpenAlex 摘要。

两个绕不开的实现原因：

- **Calibre 做不到按大类配额**：它只有 `max_articles_per_feed` 一个**全局**开关，所以配额必须自己写，Calibre 收到的是已经挑好的那几条。
- **书名不在命令行传**：`ebook-convert` 没有 `--metadata-set`（那是 `ebook-meta` 的选项），所以由 `parse_index()` 读 `picked.json` 里的 `book` 覆盖 `self.title`。

加新源之前先验：

```bash
python scripts/check_feeds.py                       # 可达性 + 最新一条是几天前的
python scripts/pick_articles.py --book science --print-only   # 看看新源有没有真选出东西
```

**光看能不能返回 200 会被骗**——这次就抓出几个"返回上百条、其实停在旧快照"的死源：

| 情况 | 源 |
| --- | --- |
| 本机可用 | 现役源 `check_feeds.py` 全绿（最新条目 0–2 天内） |
| **返回 200、上百条，但停更**（已剔除） | 人民网 时政/国际（停在 2025-06-05）、新浪科技滚动（停在 2018-09-23） |
| 404 / 500 / 返回 HTML（已剔除） | APS PRL、IOP 老式 `/rss/ISSN`（要用 `/journal/rss/ISSN`）、Nature Communications、Scientific American、Phys.org 子频道、光明网、环球、观察者网、CSDN、ChinaDaily、果壳、ScienceDaily、AP Top News、New Yorker、联合早报 / 36氪 / 机器之心 / cnBeta（返回 HTML）、`rsshub.app` 全系 |
| 要代理（走 7897 实测 200） | Guardian、BBC、NYT、Economist、FT、Google News、Aeon、The Atlantic |

顺带一句：《Science》的公开新闻 RSS 是通的（`www.science.org/rss/news_current.xml`），已放进物理那本；它只有新闻栏目，不含论文正文。

## 云端跑

改了 `.github/workflows/daily-brief.yml` 先本地校验：

```bash
python scripts/check_workflow.py
```

云端默认出哪几本由配方里的 `CLOUD_BOOKS` 决定（当前是 `daily`、`current_world`、`essays`）：定时任务按清单逐本出，一本挂了不影响其它本；手动 Run workflow 时可以填 `book` 参数只出某一本书。产物是一个含所有 epub 的 artifact，`briefs/` 每种书各留最近 14 期；配好 SMTP Secrets 后每本各发一封邮件（主题带书名，Kindle 那边分得清）。

首次部署（约 5 分钟）：

1. GitHub 新建仓库（私有也行）。
2. 上传全部文件（含 `.github/`），提交到默认分支。
3. **Settings → Actions → General → Workflow permissions** 选 **Read and write permissions**，否则归档那步 `git push` 会 403。
4. **Actions → 每日科学简报 → Run workflow**（`book` 留空 = 按 `CLOUD_BOOKS` 全出）。
5. 成果在三个地方：Summary 页的源自检表 + 出书清单、页面底部 **Artifacts**、仓库 `briefs/` 的新提交。

只有 `schedule` 会跑在默认分支；`workflow_dispatch` 和 `push` 可以跑在任意分支，方便先试。

### cron 用 UTC，比北京时间早 8 小时

| 想要的北京时间 | cron |
| --- | --- |
| 08:00（当前默认） | `0 0 * * *` |
| 07:30 | `30 23 * * *`（前一天 UTC） |
| 12:00 | `0 4 * * *` |
| 08:00 + 20:00 | `0 0,12 * * *` |
| 工作日 09:00 | `0 1 * * 1-5` |

GitHub 高峰期定时可能延迟十几分钟甚至偶尔跳过，是平台行为。

## 本地和云端差在哪

两边跑的是同一个 `build_brief.py`，正文、版式、选题规则完全一样。真正的差别只有这些：

| | 本地 bat | 云端 Actions |
| --- | --- | --- |
| 电脑要不要开着 | 要（定时也得开机） | 不要 |
| **网络可达性** | 国内直连：国外两组要代理，且代理节点会抽 | 海外 runner：Guardian/BBC/NYT 直接可达；但 rsshub 公共实例对云端 IP 限流 403 |
| 邮件 / 推 Kindle | 自己执行 `send_email.py`，密码放环境变量 | 配好 Secrets 后每本自动一封 |
| 历史归档 | 本地 `out/`，每本留 14 份 | 仓库 `briefs/` + Actions 产物 30 天 |
| 去重 | `state/seen.json` 一直累积，同日重复点和跨天都有效 | 每次运行是干净环境 → **同一天内有效，跨天清零**；要真正跨天去重得把 `state/` 一起提交回仓库 |
| 成本 | 电费 | 私有仓库每月 2000 分钟免费额度，本任务约 1–3 分钟 |
| 隐私 | 全在本地 | Actions 日志里有本期标题列表 |

这一行是本地方案唯一实打实比云端好的地方。

## 打开邮件推送（可选）

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

本地发某一本：

```bash
SMTP_HOST=smtp.qq.com SMTP_PORT=465 SMTP_USER=you@qq.com SMTP_PASS=授权码 \
MAIL_TO=reader@example.com python3 scripts/send_email.py out/科学前沿速递-2026-10-28-221440.epub
```

**发给 Kindle**：`MAIL_TO` 换成 `xxx@kindle.com`（国行 `@kindle.cn`），先在亚马逊 **Manage Your Content and Devices → Preferences → Personal Document Settings** 把发件邮箱加进 Approved list，否则静默退信。现在一本约 0.1–0.2 MB（摘要 + 少量图），离 10 MB 限制很远。

## 故障排查

| 现象 | 原因 | 处理 |
| --- | --- | --- |
| `没找到 ebook-convert` | 没装 Calibre，或装在别处 | 装 [Calibre](https://calibre-ebook.com/download_windows)，或设 `EBOOK_CONVERT` 指向 exe |
| `一篇都没选到` | 该类源都连不上，或全被去重挡掉 | `python scripts/pick_articles.py --book <书> --no-history --print-only` 看是哪一步空的 |
| 时事国际 / 深度长文空着 | 代理没走通（节点挂了、端口不对） | 看有没有"检测到本机代理"那行；`--no-proxy` 可关掉自动探测；或交给云端 |
| 某段 `2/3`（少一篇） | 该类候选被去重耗尽，或有的源当天没更新 | 正常；连点几次会越来越少，隔天自然恢复 |
| 前沿某篇只有标题 | Elsevier 的 RSS 只有标题，OpenAlex 也常缺 | 已让自带摘要的源优先；要更准就收紧 `TOPIC_KEYWORDS` |
| 中文 echo 乱码（bat 窗口） | 终端代码页 | bat 里已 `chcp 65001`；不影响出书 |
| 装 Calibre 那步超时（云端） | 下载 ~100MB 偶发慢 | 重跑 |
| `git push` 403（云端） | Workflow permissions 还是只读 | 改 Read and write |
| SMTP 认证失败 | 用了网页登录密码 | 换授权码 / App Password |
| 云端每天推同样的文章 | 干净环境里 `state/` 每次清零 | 归档那步顺手 `git add state/` |

## 关于这份实现的可靠性

实测过的：

- **本地整条链路真跑通**：Calibre 9.17（`D:\Program\Calibre2`）出过 `每日科学简报`（7 篇 / 0.16 MB）、`科学前沿速递` 连续两期（各 3 篇、文章不重复、文件名不覆盖）、`时事国际`（走代理，2 篇）。
- **书名跟着书走**：`ebook-meta` 核对过成品标题是 `时事国际 [2026-10-28]`。
- **配方字段**：`language`、`publication_type`、`timefmt`、`max_articles_per_feed`、`oldest_article`、`remove_empty_feeds`、`ignore_duplicate_articles`、`use_embedded_content`、`compress_news_images*`、`scale_news_images`、`conversion_options`、`feeds`，以及 `parse_index(self)` 返回 `[(章节, [文章 dict])]` 的写法，都对照 Calibre 9.17 源码确认（本机 `calibre-debug` 查签名 + 官方 `news.py`、`feeds/__init__.py`、`feeds/templates.py`）。旧教程里的 `language_code`、`timeofprint` 已不是有效字段。
- **源**：现役源本机 `check_feeds.py` 全绿；探测中剔掉了上面那张表里的死源和坏地址。
- **脚本**：`scripts/*.py` 通过 `python -m py_compile`；`pick_articles.py` / `build_brief.py` / `check_feeds.py` 都真实跑过（并发抓取、失败重试、OpenAlex 补摘要、同日去重）。
- **workflow**：`python scripts/check_workflow.py` 通过——14 个步骤、无悬空 `steps.*.outputs` 引用、9 个 bash 块全部 `bash -n` 通过、内嵌 Python 可编译。

没验证的：

- **这条 workflow 仍没在真实 GitHub 仓库上跑过**（要有你的仓库才能触发）。它和本地跑的是同一个 `build_brief.py`，风险集中在云端装 Calibre 那一步。
- **OpenAlex 摘要覆盖率**：Elsevier 经常缺，实测约三分之一。
- 云端 runner 侧的源可达性（和国内结论常常相反，跑完看 Summary）。

## 可选扩展

- **去重历史上云**：归档那步顺手 `git add state/`。
- **加一本**：`BOOKS` 加一行 + 复制一个 bat。
- **输出 MOBI/AZW3**：`ebook-convert 输入.epub 输出.azw3`，或 `--output-profile` 适配设备。
- **阅读器直接订阅**：Calibre-Web / OPDS 同步 `out/`，省掉邮件。
- **中文导语**：标题现在是英文原样。要每篇配一句中文摘要得接翻译，属于另一个改动。

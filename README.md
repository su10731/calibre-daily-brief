# 每日科学简报：Calibre + GitHub Actions

每天定时在 GitHub 的免费 runner 上跑一次 Calibre，把十几个科学与时事 RSS 源抓成**一本 EPUB**（《每日科学简报》，每个源是一个章节），存进仓库的 `briefs/` 目录并上传为 Actions 产物；等你想发邮件时，只要加几个 Secrets，同一条流水线会自动多出「邮件推送」这一步。

不需要自己电脑常开，不需要服务器。

## 文件结构

```
.github/workflows/daily-brief.yml   流水线：定时 → 装 Calibre → 自检源 → 生成 EPUB → 归档 / 发邮件
recipes/daily-science-brief.recipe  Calibre 新闻配方，订阅源清单就在这里改
scripts/check_feeds.py              订阅源可达性自检（纯标准库）
scripts/send_email.py              SMTP 发信（纯标准库，默认不启用）
briefs/                             Actions 自动写入，保留最近 14 期
```

## 跑起来（约 5 分钟）

1. 在 GitHub 新建一个仓库（私有也可以；私有仓库走每月 2000 分钟免费额度，本任务单次约 2–4 分钟）。
2. 把本目录的所有文件（含 `.github/`）上传到仓库根目录，提交到默认分支。
3. 仓库 **Settings → Actions → General → Workflow permissions** 选 **Read and write permissions**（否则最后一步 `git push` 归档会 403）。
4. **Actions → 每日科学简报 → Run workflow** 手动跑一次，先看绿色的对勾。
5. 跑完在三个地方能看到成果：这次运行的 Summary 页（含源自检表和本期大小）、页面底部的 **Artifacts** 下载、仓库 `briefs/` 里的新提交。

只有 `schedule` 定时触发会跑在默认分支上；`workflow_dispatch` 和 `push` 触发可以跑在任意分支，方便你先在分支上试。

## 定时时间（cron 用 UTC，比北京时间早 8 小时）

改 `.github/workflows/daily-brief.yml` 里的 `cron`：

| 想要的北京时间 | cron 写法 |
| --- | --- |
| 08:00 | `0 0 * * *`（当前默认） |
| 07:30 | `30 23 * * *`（前一天的 UTC） |
| 12:00 | `0 4 * * *` |
| 每天 08:00 + 20:00 | `0 0,12 * * *` |
| 工作日 09:00 | `0 1 * * 1-5` |

不确定就丢给 [crontab.guru](https://crontab.guru/) 生成。另外 GitHub 高峰期定时任务可能延迟十几分钟甚至偶尔跳过，这是平台行为，不是脚本坏了。

## 改订阅源

打开 `recipes/daily-science-brief.recipe`，改顶部的 `FEEDS` 列表，一行一个源：

```python
FEEDS = [
    ('Quanta Magazine', 'https://www.quantamagazine.org/feed/'),
    # ('知乎热榜', 'https://rsshub.app/zhihu/hot'),   ← 前面加 # 就是临时停用
]
```

加新源之前先本地验一下地址对不对：

```bash
python3 scripts/check_feeds.py recipes/daily-science-brief.recipe
```

三个要知道的限制：

- **每源取几篇是全局设置**（`max_articles_per_feed`，当前 8），Calibre 不支持按源分别设上限。想给某个源多取几篇，只能给它单开一个配方文件。
- `oldest_article = 3.0` 表示只收 3 天内的文章；某个源当天没更新就不会出现在书里（`remove_empty_feeds = True`）。
- 去重只在**同一天内**生效。跨天去重需要把历史标题存进仓库或 Actions 缓存再比对，属于可选扩展（见文末）。

当前默认清单（科学 10 源 + 时事 3 源）的来源与验证情况：

| 源 | 说明 |
| --- | --- |
| MIT Technology Review、Quanta、Nature、Phys.org、arXiv cs.AI/CV、Hacker News、少数派、科学网、Guardian、BBC、Google News | 本机一次探测全部 200 且解析出条目（`check_feeds.py` 首次运行 12/13 可用） |
| 雷锋网 AI（`leiphone.com/feed`） | 用来替代机器之心，实测 200 / 20 条 |
| 机器之心（`jiqizhixin.com/rss`）、36氪（`36kr.com/feed`） | **两次都返回 200 但内容是 HTML 而非 RSS**，收录只会得到空章节，已移出清单并写在配方的注释里 |
| 爱范儿、InfoQ 中文、开源中国 | 实测可用，写在配方的注释里，按需取消注释启用 |
| 澎湃、知乎热榜、Readhub | 依赖 `rsshub.app` 公共实例：本机是 SSL 握手失败（被墙），海外 runner 能连但公共实例经常对云端 IP 限流 403。默认注释掉，自建 RSSHub 后再打开 |
| Reuters | 官方 RSS 已于 2020 年下线，用 Google News 关键词源替代 |

一个必须知道的现实：**本机探测和 runner 探测会给出不同答案**。我在国内网络连续跑两次自检，第一次 12/13 可用，第二次因为代理链路抖动只有 4/13 可用，海外站点整批连接失败——这不是源坏了。所以真正算数的是流水线里那个自检步骤的输出，跑完后在 Summary 页看 runner 侧那张表，再决定增删哪些源。


## 打开邮件推送（可选）

在仓库 **Settings → Secrets and variables → Actions → New repository secret** 里加：

| Secret | 例子 |
| --- | --- |
| `SMTP_HOST` | `smtp.qq.com` |
| `SMTP_PORT` | `465`（SSL）或 `587`（STARTTLS） |
| `SMTP_USER` | `you@qq.com` |
| `SMTP_PASS` | **授权码 / 应用专用密码**，不是网页登录密码 |
| `MAIL_TO` | `reader@example.com`，多个用逗号分隔 |
| `MAIL_FROM` | 可选，多数邮箱必须等于 `SMTP_USER` |

各家邮箱拿授权码的位置：QQ 邮箱在 设置 → 账户 → POP3/IMAP/SMTP 服务里「生成授权码」；163/126 在 设置 → POP3/SMTP/IMAP 里开客户端授权密码；Gmail 需要先开两步验证再生成 App Password；Outlook.com 现在也要求应用密码。

配好后下一次运行会自动执行「邮件推送」这一步，没配就打印一行「跳过」，不影响出书。想手动补发历史某一期，本地跑：

```bash
SMTP_HOST=smtp.qq.com SMTP_PORT=465 SMTP_USER=you@qq.com SMTP_PASS=授权码 \
MAIL_TO=reader@example.com python3 scripts/send_email.py briefs/daily-science-brief-2026-10-28.epub
```

**发给 Kindle** 也能用这套：把 `MAIL_TO` 换成你的 `xxx@kindle.com`（国行账号是 `@kindle.cn`），并先在亚马逊 **Manage Your Content and Devices → Preferences → Personal Document Settings** 里把发件邮箱加入 Approved list，否则会静默退信。Send-to-Kindle 对附件大小有限制，配方里已把单张图片压到 120 KB、每源 8 篇，正常一本在几 MB 以内；超过 10 MB 流水线会在日志里给出提示。

## 本地先试一次（可选）

Windows 装 [Calibre](https://calibre-ebook.com/download_windows) 后，在仓库根目录执行（PowerShell）：

```powershell
& "C:\Program Files\Calibre2\ebook-convert.exe" recipes\daily-science-brief.recipe 测试.epub
```

生成的 `.epub` 双击用 Calibre 打开就能看到分章效果。注意本地网络可能拦掉部分源，日志里出现个别 `FAILED to download and parse` 不会中断整本书。

## 故障排查

| 现象 | 原因 | 处理 |
| --- | --- | --- |
| 装 Calibre 那一步超时 | 下载 ~100MB 二进制包偶发慢 | 重跑一次；或给自己仓库加一个 Actions 缓存步骤 |
| 某章整章缺失 | 该源 403 / 反爬 / 需要 RSSHub | 看 Summary 的自检表，停用或换成可用镜像源 |
| 整本书几乎是空的 | 全部源在 runner 侧不可达 | 自检表会告诉你；先减到 2–3 个源验证链路，再加回来 |
| `git push` 报 403 | Workflow permissions 还是只读 | Settings → Actions → General 改成 Read and write |
| 邮件步骤没出现 | `SMTP_HOST` 名字写错或没加到 Actions secrets | 检查 secret 名称大小写完全一致 |
| SMTP 认证失败 | 用了网页登录密码 | 换成授权码 / App Password |
| 定时不触发 | 非默认分支、Actions 被暂停（欠费或连续失败）、平台延迟 | Actions 页面看是否有「暂停」提示，或先手动跑一次 |
| EPUB 太大 | 源多、图片多 | 调小 `max_articles_per_feed`、`compress_news_images_max_size`、`oldest_article` |

## 关于这份实现的可靠性

已经验证过的部分：

- **配方字段**：`language`、`publication_type`、`timefmt`、`max_articles_per_feed`、`oldest_article`、`remove_empty_feeds`、`ignore_duplicate_articles`、`compress_news_images` / `compress_news_images_max_size`、`scale_news_images`、`conversion_options`、`feeds` 全部对照 Calibre 源码 `src/calibre/web/feeds/news.py` 确认存在、拼写正确、取值合法（旧教程里常见的 `language_code`、`timeofprint` 现在已不是有效字段；`feeds` 只接受 `(标题, URL)` 二元组）。
- **订阅源**：`check_feeds.py` 实测过全部候选源，并因此发现机器之心、36氪 已不再输出 RSS，改成了雷锋网。
- **脚本**：`recipes/*.recipe`、`scripts/*.py` 通过 `python -m py_compile`；`check_feeds.py` 在本机真实跑通过（含并发探测与失败重试）。
- **工作流**：YAML 能被 `yaml.safe_load` 解析，10 个 step 的 id 引用无悬空，每个 `run` 块单独提出来过 `bash -n` 语法检查；Calibre 安装命令和邮件做法来自官方下载页与书伴的同类实践。

还没验证的部分：**这条 workflow 没有在真实 GitHub 仓库上实跑过**（要有你的仓库才能触发），本机也没有装 Calibre，所以「`ebook-convert` 真的产出一本 EPUB」这一步还没跑通。所以上面第 4 步的手动运行就是第一次真正的验收；按经验最可能需要微调的是 apt 依赖和个别源，而不是配方语法。


## 可选扩展

- **跨天去重**：把每期标题列表写进 `seen.json` 提交回仓库，配方启动时读它并过滤重复条目。
- **拆成多本**：复制一份配方文件改 `title` 和 `FEEDS`，workflow 里加一步再生成一次，一天收两本（科学 / 时事）。
- **输出 MOBI/AZW3**：在 `ebook-convert` 后再跑一次 `ebook-convert 输入.epub 输出.azw3`，或加 `--output-profile` 适配具体设备。
- **阅读器直接订阅**：配 Calibre-Web / OPDS，把 `briefs/` 同步过去，省掉邮件。
- **全文抓取**：RSS 只有摘要的源，可在配方里设 `use_embedded_content = False` 让它下载网页正文，代价是慢和更容易被反爬。

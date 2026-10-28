#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
把生成的 EPUB 用 SMTP 发到你的邮箱（可选步骤，默认不启用）。

需要先配置这些环境变量（在 GitHub Actions 里就是仓库 Secrets）：

    SMTP_HOST   smtp.qq.com / smtp.163.com / smtp.gmail.com ...
    SMTP_PORT   465（SSL）或 587（STARTTLS）
    SMTP_USER   登录用的完整邮箱地址
    SMTP_PASS   授权码 / 应用专用密码（不是网页登录密码）
    MAIL_TO     收件人，多个用逗号分隔
    MAIL_FROM   可选，缺省等于 SMTP_USER；部分邮箱要求两者一致
    MAIL_SUBJECT 可选，缺省用第一个附件的文件名

用法：
    SMTP_HOST=smtp.qq.com SMTP_PORT=465 SMTP_USER=a@qq.com SMTP_PASS=授权码 \
    MAIL_TO=b@example.com python3 scripts/send_email.py out/daily-science-brief-2026-10-28.epub

只用标准库，不需要 pip install。
"""

import os
import smtplib
import ssl
import sys
from email.message import EmailMessage
from email.utils import formatdate, make_msgid

MIME_BY_EXT = {
    '.epub': ('application', 'epub+zip'),
    '.mobi': ('application', 'x-mobipocket-ebook'),
    '.azw3': ('application', 'vnd.amazon.ebook'),
    '.pdf': ('application', 'pdf'),
    '.txt': ('text', 'plain'),
}


def die(msg, code=2):
    print(f'!! {msg}', file=sys.stderr)
    sys.exit(code)


def main():
    files = [a for a in sys.argv[1:] if not a.startswith('-')]
    if not files:
        die('用法：send_email.py 附件1.epub [附件2.epub ...]')
    for path in files:
        if not os.path.isfile(path):
            die(f'附件不存在：{path}')

    host = os.environ.get('SMTP_HOST', '').strip()
    user = os.environ.get('SMTP_USER', '').strip()
    password = os.environ.get('SMTP_PASS', '').strip()
    recipients_raw = os.environ.get('MAIL_TO', '').strip()
    if not (host and user and password and recipients_raw):
        die('SMTP_HOST / SMTP_USER / SMTP_PASS / MAIL_TO 四个变量必须都配好')

    port = int(os.environ.get('SMTP_PORT', '465') or 465)
    sender = os.environ.get('MAIL_FROM', '').strip() or user
    recipients = [r.strip() for r in recipients_raw.replace(';', ',').replace(' ', ',').split(',') if r.strip()]

    subject = os.environ.get('MAIL_SUBJECT', '').strip()
    if not subject:
        subject = os.path.splitext(os.path.basename(files[0]))[0]

    msg = EmailMessage()
    msg['Subject'] = subject
    msg['From'] = sender
    msg['To'] = ', '.join(recipients)
    msg['Date'] = formatdate(localtime=True)
    msg['Message-ID'] = make_msgid()
    msg.set_content(
        '这是定时任务自动生成的电子书，直接下载附件用阅读器打开即可。\n'
        '如果是发往 Kindle：Kindle 会把它转成可阅读格式，通常需要几十秒到几分钟同步。\n\n'
        f'附件：{", ".join(os.path.basename(f) for f in files)}\n'
    )

    total = 0
    for path in files:
        maintype, subtype = MIME_BY_EXT.get(os.path.splitext(path)[1].lower(), ('application', 'octet-stream'))
        with open(path, 'rb') as fh:
            data = fh.read()
        total += len(data)
        msg.add_attachment(data, maintype=maintype, subtype=subtype,
                           filename=os.path.basename(path))
        print(f'附加 {path}（{len(data) / 1024 / 1024:.1f} MB）')

    if total > 20 * 1024 * 1024:
        print('警告：附件合计超过 20 MB，多数邮箱（包括 Kindle）可能拒收。', file=sys.stderr)

    ctx = ssl.create_default_context()
    if port == 465 or os.environ.get('SMTP_SSL') == '1':
        server = smtplib.SMTP_SSL(host, port, timeout=60, context=ctx)
    else:
        server = smtplib.SMTP(host, port, timeout=60)
        server.ehlo()
        if server.has_extn('starttls'):
            server.starttls(context=ctx)
            server.ehlo()
        else:
            print('警告：服务器不支持 STARTTLS，将使用明文连接。', file=sys.stderr)

    with server:
        try:
            server.login(user, password)
        except smtplib.SMTPAuthenticationError as exc:
            die(f'登录失败，请确认用的是「授权码 / 应用专用密码」而不是网页登录密码：{exc}', 3)
        refused = server.send_message(msg, from_addr=sender, to_addrs=recipients)
        if refused:
            die(f'部分收件人被拒收：{refused}', 4)
    print(f'已发送给：{", ".join(recipients)}')
    return 0


if __name__ == '__main__':
    sys.exit(main())

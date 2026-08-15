# 电影开票监测器

这是一个可直接部署到 GitHub Actions 的 Python 电影开票监测项目。默认目标已经配置为：

- 影院：MOViE MOViE 影城（前滩太古里店）
- 影片：《奥德赛》（猫眼影片 ID `1545360`）
- 日期：2026-08-21
- 检查频率：每 10 分钟
- 通知：SMTP 邮件；可选 PushPlus 微信推送

项目不依赖本地电脑持续开机。它会合并多个来源的结果，在首次出现可售场次或后来新增场次时通知一次。相同场次不会重复通知。

## 当前数据源设计

1. `maoyan_json`（主源）：读取猫眼移动站公开的结构化影院场次数据。它能拿到日期、时间、影厅、语言、制式、场次号和售票状态，默认仅把 `ticketStatus=0` 视为可售。
2. `maoyan_html_fallback`（备用解析通道）：读取猫眼公开影院 HTML。只有页面在目标影片区块内同时出现目标日期、具体时间和“选座购票/购票/预售”按钮时才会判定可售，宁可漏报也不根据模糊文本误报。

两个来源会在每次任务中都运行。一个失败时，另一个仍可完成判断；两个都失败时任务以非零状态退出，GitHub Actions 会标红并保留日志。由于国内售票平台经常把 App/小程序接口设为动态签名或登录态，默认配置没有伪造淘票票私有 API；这种方式比依赖随时失效的逆向签名更适合长期维护。

百老汇影城官方 App、小程序、猫眼和淘票票均是该影院的购票渠道。当前可公开、免登录且已实际验证的结构化入口是猫眼，因此项目默认以猫眼为主。购票动作始终在官方售票页面完成，程序不会代下单、不会保存购票账号或支付信息。

## 项目结构

```text
movie-ticket-watcher/
├── .github/workflows/watch.yml    # GitHub Actions：每 10 分钟运行并持久化状态
├── movie_watcher/
│   ├── cli.py                     # 命令行入口、退出码、日志
│   ├── config.py                  # YAML 配置加载与校验
│   ├── http.py                    # HTTP 会话和指数退避重试
│   ├── models.py                  # 目标、场次、来源结果模型
│   ├── service.py                 # 多源合并、判定、去重、通知编排
│   ├── state.py                   # 原子化状态读写和月度心跳
│   ├── sources/
│   │   ├── maoyan.py              # 猫眼 JSON 主源和 HTML 备用源
│   │   └── base.py
│   └── notifiers/
│       ├── email.py               # SMTP SSL / STARTTLS 邮件
│       ├── pushplus.py            # 可选的微信推送
│       └── base.py
├── runtime/state.json             # 已通知场次；Actions 会自动提交这个文件
├── tests/                         # JSON/HTML 解析和去重测试
├── config.yaml                    # 已填好本次目标的生产配置
├── config.example.yaml            # 未来目标配置模板
├── .env.example                   # 本地环境变量示例
├── requirements.txt               # 运行依赖
└── requirements-dev.txt           # 测试依赖
```

运行日志同时输出到控制台和 `runtime/watcher.log`，本地日志自动轮转（每个 2 MB，保留 3 份）。GitHub 上可在每次 Actions 运行的 `Check ticket availability` 步骤查看完整日志。

## 一、先在本地验证（推荐）

需要 Python 3.9 或更新版本。

```bash
python3 -m venv .venv
source .venv/bin/activate
python -m pip install -r requirements-dev.txt
pytest
python -m movie_watcher.cli --dry-run --verbose
```

`--dry-run` 会访问真实数据源，但不发送通知，也不写入已通知场次。当前没有 8 月 21 日可售场次时，日志中应看到 `no new sellable sessions`。

### 本地测试邮件

复制 `.env.example` 中的变量到当前 shell（不要把真实密码写进仓库），然后运行：

```bash
export SMTP_HOST="smtp.qq.com"
export SMTP_PORT="465"
export SMTP_USERNAME="你的邮箱@qq.com"
export SMTP_PASSWORD="SMTP 授权码，不是登录密码"
export SMTP_FROM="你的邮箱@qq.com"
export SMTP_TO="接收提醒的邮箱"
python -m movie_watcher.cli --test-notification
```

常见 SMTP 设置：

| 邮箱 | 主机 | 端口 | 配置 |
|---|---|---:|---|
| QQ 邮箱 | `smtp.qq.com` | 465 | `use_ssl: true` |
| 163 邮箱 | `smtp.163.com` | 465 | `use_ssl: true` |
| Gmail | `smtp.gmail.com` | 465 | `use_ssl: true`，使用应用专用密码 |
| Outlook | `smtp.office365.com` | 587 | `use_ssl: false`、`use_starttls: true` |

若使用 587/STARTTLS，请同步修改 `config.yaml` 的两个布尔值。

## 二、部署到 GitHub Actions

### 1. 建立仓库并上传项目

在 GitHub 新建空仓库，把本目录全部文件提交到默认分支（通常是 `main`）。工作流文件必须位于默认分支才会按时运行。

```bash
git init
git add .
git commit -m "Deploy movie ticket watcher"
git branch -M main
git remote add origin https://github.com/你的用户名/你的仓库名.git
git push -u origin main
```

如果这是已有仓库，只需正常提交并推送这些文件，不要再次运行 `git init`。

### 2. 添加邮件 Secrets

打开仓库：`Settings` → `Secrets and variables` → `Actions` → `New repository secret`，添加：

| Secret | 内容 |
|---|---|
| `SMTP_HOST` | 例如 `smtp.qq.com` |
| `SMTP_PORT` | 例如 `465` |
| `SMTP_USERNAME` | 发件邮箱账号 |
| `SMTP_PASSWORD` | SMTP 授权码/应用密码 |
| `SMTP_FROM` | 发件地址，通常同账号 |
| `SMTP_TO` | 收件地址；多个地址用英文逗号分隔 |

Secrets 不会写进代码或状态文件。不要把 `.env`、邮箱密码或 PushPlus token 提交到仓库。

### 3. 手动测试一次

打开 `Actions` → `Movie ticket watcher` → `Run workflow`：

1. 首次选择 `dry_run = true`、`test_notification = false`，确认数据源日志正常。
2. 再选择 `dry_run = false`、`test_notification = true`，它会跳过票源检查并发送一条明确标注为测试的通知。
3. 测试成功后，手动运行一次两个开关都为 `false` 的正常检查。如果当前没有票，它不会发信，这是正常的。

之后工作流会在每小时的第 3、13、23、33、43、53 分钟自动运行。GitHub 的 cron 不是实时系统，平台繁忙时可能延迟或极少数丢弃；工作流特意避开整点和半点来降低延迟风险。

### 4. 确认状态可以持久化

发现新场次并成功发出至少一种通知后，工作流会自动提交更新后的 `runtime/state.json`。仓库需允许 Actions 写入：

`Settings` → `Actions` → `General` → `Workflow permissions` → `Read and write permissions`

工作流也声明了 `contents: write`。如果默认分支保护规则禁止机器人直接 push，需要给 `github-actions[bot]` 放行，或为这个小型监测仓库取消该分支的 push 限制。

## 三、可选微信通知

项目使用 PushPlus 的免费微信公众号渠道：

1. 登录 [PushPlus](https://www.pushplus.plus/)，关注并绑定其微信公众号，取得 token。
2. 在 GitHub Actions Secrets 添加 `PUSHPLUS_TOKEN`。
3. 把 `config.yaml` 中 `notifications.pushplus.enabled` 改成 `true` 后提交。

邮件和微信都启用时会尝试同时发送。只要至少一个渠道成功，场次就会记入去重状态；失败渠道会在日志中明确记录。若你希望“两个渠道必须都成功才算通知成功”，可调整 `service.py` 的 `notify` 策略。

## 去重和状态变化规则

每个可售场次会按以下字段生成稳定指纹：

```text
日期 + 开场时间 + 影厅 + 语言 + 制式
```

- 从无票变为有票：新指纹，提醒。
- 已有场次后来增加一场：只提醒新增场次。
- 同一场次由 JSON 和 HTML 同时发现：先合并，只提醒一次。
- 已通知场次暂时售罄后又恢复：不会重复提醒。
- 通知发送失败：不写入指纹，下次检查会自动重试通知。
- 网络或平台临时错误：HTTP 最多自动重试 3 次并指数退避；所有来源都失败时任务标红。

如果确实想让某场重新提醒，可在 `runtime/state.json` 中删除该目标的相应指纹；最简单的完全重置方法是删除该目标 ID 对应的整个对象，但不要删除 JSON 外层结构。

## 修改监测目标

编辑 `config.yaml` 的 `target`：

```yaml
target:
  id: 一个新的唯一名称
  cinema_name: "影院名称"
  cinema_id: "猫眼影院 ID"
  movie_name: "影片名称"
  movie_id: "猫眼影片 ID"
  date: "YYYY-MM-DD"
  timezone: "Asia/Shanghai"
  buy_url: "猫眼影院购票页"
```

猫眼影院 ID 通常在影院网址 `/cinema/37534` 中，影片 ID 通常在影片网址 `/films/1545360` 中。每次换目标都应更换 `target.id`，这样旧目标的去重状态不会影响新目标。

`runtime.stop_after_target_days: 1` 表示目标日期结束一天后停止发起售票网络请求，但 Actions 仍会快速启动并退出。修改为更大的数可延长监测，设为负数并不会表示无限期；若要长期轮换目标，建议按需更新日期和 ID。

## 费用和长期运行注意事项

- GitHub 官方说明：标准 GitHub-hosted runner 用于公开仓库时，Actions 分钟免费；私有仓库按账户套餐有月度免费额度。10 分钟一次约为每月 4,320 次运行，而私有仓库的每次用量按分钟计，因此长期免费运行更适合一个不含任何密钥明文的公开仓库。Secrets 即使仓库公开也不会展示，但只应让可信用户拥有写权限。
- 本目标距离 2026-08-21 很近，即使使用私有仓库，短期运行通常远少于整月 4,320 次；仍请在 GitHub Billing 页面查看自己的实际额度。
- 公开仓库若连续 60 天没有活动，GitHub 可能自动停用定时工作流。项目每 30 天更新一次 `state.json` 心跳并自动提交，以保持仓库活动。若分支保护阻止心跳提交，需定期手动提交或重新启用工作流。
- 任务在目标过期后仍会按 cron 启动。完成购票后，可在 `Actions` → `Movie ticket watcher` 菜单中选择 `Disable workflow`；也可在仓库变量中添加 `WATCHER_ENABLED=false` 暂停定时任务，手动运行仍可用。
- 售票平台可能更改页面或启用反爬策略。项目会把源失败写入日志，但无法保证第三方平台永不变更。建议同时开启 GitHub Actions 失败通知，并在临近开票时偶尔人工核对购票 App。

## 常用命令

```bash
# 真实检查；仅在有新增可售场次时通知
python -m movie_watcher.cli

# 真实抓取但不通知、不写去重状态
python -m movie_watcher.cli --dry-run --verbose

# 不抓售票数据，只测试已启用通知渠道
python -m movie_watcher.cli --test-notification

# 运行测试
pytest
```

程序退出码：`0` 成功、`2` 所有数据源失败、`3` 所有通知渠道失败、`4` 配置错误、`1` 其他未预期错误。

## 合规说明

项目每 10 分钟只请求少量公开页面，不绕过登录、验证码、付费墙或支付流程。请遵守售票平台的服务条款和 robots/访问限制；如果平台明确禁止自动访问，应关闭对应来源并改用其官方提醒功能。

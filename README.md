# 工具类 APP 热度趋势日报

此目录为经过白名单整理的源码、模板、无凭据配置及离线测试，不包含历史业务数据、认证、日志或生成报告。
目标仓库为 hjk6994/tools-daily-report，已获用户授权使用公开仓库。
当前只准备源代码，没有配置云端定时、发送任务或协作者。

## 运行环境

原流程已使用 Python 3.12.14 与 Node 24.19.0 验证。目标平台应按锁文件重新安装依赖，不复制本机二进制目录。

    python -m pip install -r requirements.lock.txt
    npm ci --prefix .deps-js

HTML 验收脚本通过相对目录 .deps-js/node_modules/jsdom 加载依赖。
PDF 辅助模块仍含 Windows 字体路径；当前日报使用 HTML，云端若启用 PDF 须另行适配字体。

## 主要入口

- daily_automation.py：增量任务规划、DSP/PalmStore 采集、Sensor Tower 观察导入、日报生成及发送入口。
- appmagic_automation.py / appmagic_growth.py：固定九国联合的每日估算免费下载排名规划、导入及周对比。
- weekly_growth.py / weekly_report.py：复算与 HTML 渲染。
- tests/check_weekly_report.cjs：已生成日报的离线验收。

克隆本仓库不会自动采集或发送。仓库未添加 GitHub Actions、cron 或云端调度配置。

## 运行前提

完整日报还需要经单独授权迁入云端持久存储的真实历史和运行状态。本仓库不提供这些数据。
真实认证只能通过用户批准的运行环境密钥管理机制使用，不得提交到 Git、报告、日志或交付包。
当前配置文件没有真实认证值。本包不包含 .env 文件、原发送账本或浏览器会话。
在认证、真实历史、去重状态及云端运行条件核验前，不运行在线采集或发送命令。

## 排名观察约定

Sensor Tower 使用 Android 工具免费榜；国家和日期来自既有增量任务清单，保存真实连续原名次及包名。
AppMagic 使用固定 PK/IN/NG/ID/BD/PH/IQ/RU/SA 九国联合、Google Play、实用工具、日、估算免费下载排序，至少100条。
不可用实时小时商店位置替代 AppMagic 每日估算下载排序，不把单国排名拼成联合榜。
日期须早于报告日；shown_date 应为 ISO 日期，shown_date_text 保留实际可见原文。
传输仅作为 JSON 数据解析，核对字节数及 SHA256；HTML 实体解码或日期规范化必须保留审计。

## 安全与测试

.gitignore 排除认证、业务数据、输出、日志、SQLite、缓存和已安装依赖。
保留的测试使用模拟或临时数据；本次整理没有重新执行在线日报或发送步骤。
历史数据与同一去重账本需要单独、安全迁移，不能通过清空账本绕过重复发送保护。

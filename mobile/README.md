# AI Schedule Agent - 移动端 (Flutter)

## 当前实现
- 登录 / 注册
- 今日概览
- 日程列表
- 新建 / 完成 / 删除任务
- Agent 对话入口
- 课表网页登录导入

## Agent 交互

- 查询“安排”“课程”“日程”时，后端会合并返回任务和课程。
- “同意 / 取消”快捷按钮只会在冲突确认阶段出现。
- Agent 回复会尽量保持秘书式语气，而不是机械回执。

## 课表导入

课表导入页面位于 `lib/screens/schedule_web_import_screen.dart`，用于从学校教务系统导入课程：

1. 内置 WebView 打开教务系统登录页。
2. 用户完成登录后，页面会自动扫描“我的课表 / 课表查询 / 课程查询 / 我的课程”等入口。
3. 找到入口后自动点击；如果已经在课表页，会自动尝试导入。
4. 点击“导入当前页”时，App 会把页面源码、同源 iframe、可见课程卡片、星期/日期表头和候选可点击控件一并提交给后端。
5. 后端接口 `/api/v1/crawl/schedule/from-html` 解析后写入课程表。

识别策略：

- 优先解析标准课程表格。
- 兼容矩阵课表，例如按星期列、节次行排布的表格。
- 当 DOM 表格不规整时，使用课程卡片的可见文本和屏幕位置兜底。
- 入口扫描不只看 `<button>`，还会检查 `a/button/input/span/div/li`、`onclick`、`role=button`、`title`、`aria-label`、`id`、`class` 和可见文字。

已知限制：

- 跨域 iframe 内部 DOM 不能被 WebView 页面脚本读取，这是浏览器安全限制。
- 如果课表完全绘制在 canvas 或图片里，当前 DOM 解析无法直接读取课程文本，需要后续截图/OCR兜底。
- 学校系统如果延迟加载较慢，等待页面稳定后再点“导入当前页”更可靠。

## 后端地址
当前默认使用 ECS 公网 IP 的 HTTP 网关地址：
- `API_BASE_URL=http://<ECS_PUBLIC_IP>`

`<YOUR_DOMAIN>` 部署在中国大陆 ECS 上，完成 ICP 备案前会被阿里云拦截。备案完成后，应将默认地址切回 `https://<YOUR_DOMAIN>`，并关闭 Android 明文流量。

本地 Android 模拟器开发时可以覆盖为：
- `APP_SERVICE_URL=http://10.0.2.2:8000`
- `AGENT_SERVICE_URL=http://10.0.2.2:8002`
- `TIMELINE_SERVICE_URL=http://10.0.2.2:8003`

如果你跑的是 iOS 模拟器或真机，把地址改成宿主机局域网 IP。

域名完成 ICP 备案后，正式公网入口使用统一 HTTPS 网关地址。当前证书已经覆盖 `<YOUR_DOMAIN>`。

生产环境建议使用统一的 HTTPS 网关地址。设置 `API_BASE_URL` 后，四个服务会共用该地址，路径由 Nginx 转发：

```bash
flutter build apk --release
```

旧的 `APP_SERVICE_URL`、`AGENT_SERVICE_URL`、`TIMELINE_SERVICE_URL`、`CRAWLER_SERVICE_URL` 参数仍然可单独覆盖，便于本地调试。

## 启动
```bash
cd mobile
flutter create . --platforms=android,ios
flutter pub get
flutter run --dart-define=APP_SERVICE_URL=http://10.0.2.2:8000 \
  --dart-define=CRAWLER_SERVICE_URL=http://10.0.2.2:8001 \
  --dart-define=AGENT_SERVICE_URL=http://10.0.2.2:8002 \
  --dart-define=TIMELINE_SERVICE_URL=http://10.0.2.2:8003
```

`flutter create .` 只需要在第一次生成平台工程时执行。

## 验证

```bash
cd mobile
dart analyze lib/screens/schedule_web_import_screen.dart
```

后端课表导入测试：

```bash
cd ..
.\venv\Scripts\python.exe -m unittest backend.tests.test_schedule_import
```

## 目录结构
```
mobile/
├── lib/
│   ├── core/
│   ├── models/
│   ├── screens/
│   ├── services/
│   ├── state/
│   └── widgets/
├── analysis_options.yaml
├── pubspec.yaml
└── README.md
```

# AI Schedule Agent - 移动端 (Flutter)

## 当前实现
- 登录 / 注册
- 今日概览
- 日程列表
- 新建 / 完成 / 删除任务
- Agent 对话入口

## 后端地址
默认使用 Android 模拟器地址：
- `APP_SERVICE_URL=http://10.0.2.2:8000`
- `AGENT_SERVICE_URL=http://10.0.2.2:8002`
- `TIMELINE_SERVICE_URL=http://10.0.2.2:8003`

如果你跑的是 iOS 模拟器或真机，把地址改成宿主机局域网 IP。

## 启动
```bash
cd mobile
flutter create . --platforms=android,ios
flutter pub get
flutter run --dart-define=APP_SERVICE_URL=http://10.0.2.2:8000 \
  --dart-define=AGENT_SERVICE_URL=http://10.0.2.2:8002 \
  --dart-define=TIMELINE_SERVICE_URL=http://10.0.2.2:8003
```

`flutter create .` 只需要在第一次生成平台工程时执行。

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

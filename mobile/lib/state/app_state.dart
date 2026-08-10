import 'package:flutter/foundation.dart';

import '../core/api/api_client.dart';
import '../core/config/api_config.dart';
import '../models/agent_chat.dart';
import '../models/auth_session.dart';
import '../models/task_item.dart';
import '../services/agent_service.dart';
import '../services/auth_service.dart';
import '../services/task_service.dart';

class AppState extends ChangeNotifier {
  AppState({this.config = ApiConfig.current});

  final ApiConfig config;

  AuthSession? _session;
  String? _agentSessionId;
  bool _busy = false;
  String? _error;
  List<TaskItem> _tasks = const [];
  List<ChatMessage> _messages = const [
    ChatMessage(role: 'assistant', content: '我是林。今天的安排、提醒和冲突都可以交给我。'),
  ];

  AuthSession? get session => _session;
  bool get isSignedIn => _session != null;
  bool get busy => _busy;
  String? get error => _error;
  List<TaskItem> get tasks => _tasks;
  List<ChatMessage> get messages => _messages;

  ApiClient get _authClient => ApiClient(baseUrl: config.appServiceUrl);

  ApiClient get _agentClient => ApiClient(
        baseUrl: config.agentServiceUrl,
        token: _session?.token,
      );

  ApiClient get _timelineClient => ApiClient(
        baseUrl: config.timelineServiceUrl,
        token: _session?.token,
      );

  Future<void> login(String username, String password) async {
    await _runBusy(() async {
      _session = await AuthService(_authClient).login(
        username: username,
        password: password,
      );
      await _loadTasks(_session!.user.id);
    });
  }

  Future<void> register({
    required String username,
    required String password,
    String? email,
  }) async {
    await _runBusy(() async {
      await AuthService(_authClient).register(
        username: username,
        password: password,
        email: email,
      );
      _session = await AuthService(_authClient).login(
        username: username,
        password: password,
      );
      await _loadTasks(_session!.user.id);
    });
  }

  void signOut() {
    _session = null;
    _agentSessionId = null;
    _tasks = const [];
    _messages = const [
      ChatMessage(role: 'assistant', content: '我是林。今天的安排、提醒和冲突都可以交给我。'),
    ];
    notifyListeners();
  }

  Future<void> refreshTasks() async {
    final current = _session;
    if (current == null) {
      return;
    }
    await _runBusy(() async {
      await _loadTasks(current.user.id);
    });
  }

  Future<void> _loadTasks(int userId) async {
    _tasks = await TaskService(_timelineClient).listTasks(userId: userId);
    _tasks = [..._tasks]..sort((a, b) => a.startTime.compareTo(b.startTime));
    notifyListeners();
  }

  Future<void> createTask({
    required String title,
    required DateTime startTime,
    required DateTime endTime,
    String? description,
    String? location,
    TaskPriority priority = TaskPriority.medium,
    TaskCategory category = TaskCategory.personal,
  }) async {
    final current = _session;
    if (current == null) {
      return;
    }
    await _runBusy(() async {
      await TaskService(_timelineClient).createTask(
        userId: current.user.id,
        title: title,
        startTime: startTime,
        endTime: endTime,
        description: description,
        location: location,
        priority: priority,
        category: category,
      );
      await _loadTasks(current.user.id);
    });
  }

  Future<void> completeTask(TaskItem task) async {
    final current = _session;
    if (current == null) {
      return;
    }
    await _runBusy(() async {
      await TaskService(_timelineClient).updateStatus(
        taskId: task.id,
        status: TaskStatus.completed,
      );
      await _loadTasks(current.user.id);
    });
  }

  Future<void> deleteTask(TaskItem task) async {
    final current = _session;
    if (current == null) {
      return;
    }
    await _runBusy(() async {
      await TaskService(_timelineClient).deleteTask(task.id);
      await _loadTasks(current.user.id);
    });
  }

  Future<void> sendAgentMessage(String content) async {
    final current = _session;
    final trimmed = content.trim();
    if (current == null || trimmed.isEmpty) {
      return;
    }
    final userMessage = ChatMessage(role: 'user', content: trimmed);
    _messages = [..._messages, userMessage];
    notifyListeners();

    await _runBusy(() async {
      final response = await AgentService(_agentClient).sendMessage(
        userId: current.user.id,
        message: trimmed,
        sessionId: _agentSessionId,
        history: _messages.take(_messages.length - 1).toList(),
      );
      _agentSessionId = response.sessionId;
      _messages = [
        ..._messages,
        ChatMessage(role: 'assistant', content: response.reply),
      ];
      if (response.tasksCreated.isNotEmpty ||
          response.tasksUpdated.isNotEmpty ||
          response.actionsTaken.isNotEmpty) {
        await _loadTasks(current.user.id);
      }
    });
  }

  void clearError() {
    _error = null;
    notifyListeners();
  }

  Future<void> _runBusy(Future<void> Function() action) async {
    _busy = true;
    _error = null;
    notifyListeners();
    try {
      await action();
    } catch (error) {
      _error = error.toString();
      rethrow;
    } finally {
      _busy = false;
      notifyListeners();
    }
  }
}

import 'dart:async';

import 'package:flutter/foundation.dart';
import '../core/api/api_client.dart';
import '../core/config/api_config.dart';
import '../models/agent_chat.dart';
import '../models/auth_session.dart';
import '../models/course_item.dart';
import '../models/schedule_import_result.dart';
import '../models/task_item.dart';
import '../models/todo_item.dart';
import '../services/agent_service.dart';
import '../services/auth_service.dart';
import '../services/crawler_service.dart';
import '../services/session_store.dart';
import '../services/task_service.dart';
import '../services/todo_service.dart';

class AppState extends ChangeNotifier {
  AppState({this.config = ApiConfig.current});

  final ApiConfig config;

  AuthSession? _session;
  String? _agentSessionId;
  bool _busy = false;
  bool _restoringSession = true;
  bool _agentThinking = false;
  bool _agentNeedsConfirmation = false;
  String _agentConfirmationStage = '';
  String? _error;
  DateTime _selectedDate = _dateOnly(DateTime.now());
  List<TaskItem> _tasks = const [];
  List<TaskItem> _todayTasks = const [];
  List<CourseItem> _courses = const [];
  List<TodoItem> _todos = const [];
  List<TodoItem> _todoHistory = const [];
  List<ChatMessage> _messages = const [
    ChatMessage(role: 'assistant', content: '我是林。今天的安排、提醒和冲突都可以交给我。'),
  ];

  AuthSession? get session => _session;
  bool get isSignedIn => _session != null;
  bool get busy => _busy;
  bool get restoringSession => _restoringSession;
  bool get agentThinking => _agentThinking;
  bool get agentNeedsConfirmation => _agentNeedsConfirmation;
  String get agentConfirmationStage => _agentConfirmationStage;
  String? get error => _error;
  List<TaskItem> get tasks => _tasks;
  List<TaskItem> get todayTasks => _todayTasks;
  List<CourseItem> get courses => _courses;
  List<TodoItem> get todos => _todos;
  List<TodoItem> get todoHistory => _todoHistory;
  List<ChatMessage> get messages => _messages;
  DateTime get selectedDate => _selectedDate;

  ApiClient get _authClient => ApiClient(baseUrl: config.appServiceUrl);

  ApiClient get _agentClient => ApiClient(
        baseUrl: config.agentServiceUrl,
        token: _session?.token,
      );

  ApiClient get _timelineClient => ApiClient(
        baseUrl: config.timelineServiceUrl,
        token: _session?.token,
      );

  ApiClient get _crawlerClient => ApiClient(
        baseUrl: config.crawlerServiceUrl,
        token: _session?.token,
      );

  Future<void> restoreSession() async {
    try {
      final restored = await SessionStore().read();
      if (restored == null) {
        return;
      }
      _session = restored;
      _agentSessionId = restored.sessionId.isEmpty ? null : restored.sessionId;
      _selectedDate = _dateOnly(DateTime.now());
      await _loadTasks(restored.user.id, _selectedDate);
      await _loadChatHistory(restored.user.id);
    } catch (error) {
      // Keep the local session when the service is temporarily unavailable.
      // The user can still retry from the signed-in shell instead of re-entering credentials.
      _error = error.toString();
    } finally {
      _restoringSession = false;
      notifyListeners();
    }
  }

  Future<void> login(String username, String password) async {
    await _runBusy(() async {
      _session = await AuthService(_authClient).login(
        username: username,
        password: password,
      );
      await SessionStore().save(_session!);
      _agentNeedsConfirmation = false;
      _agentConfirmationStage = '';
      _selectedDate = _dateOnly(DateTime.now());
      await Future.wait([
        _loadChatHistory(_session!.user.id),
        _loadTasks(_session!.user.id, _selectedDate),
      ]);
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
      await SessionStore().save(_session!);
      _agentNeedsConfirmation = false;
      _agentConfirmationStage = '';
      _selectedDate = _dateOnly(DateTime.now());
      await Future.wait([
        _loadChatHistory(_session!.user.id),
        _loadTasks(_session!.user.id, _selectedDate),
      ]);
    });
  }

  void signOut() {
    final token = _session?.token;
    _session = null;
    _agentSessionId = null;
    _agentNeedsConfirmation = false;
    _agentConfirmationStage = '';
    _tasks = const [];
    _todayTasks = const [];
    _courses = const [];
    _todos = const [];
    _todoHistory = const [];
    _messages = const [
      ChatMessage(role: 'assistant', content: '我是林。今天的安排、提醒和冲突都可以交给我。'),
    ];
    notifyListeners();
    unawaited(SessionStore().clear());
    if (token != null && token.isNotEmpty) {
      unawaited(AuthService(_authClient).logout(token: token));
    }
  }

  Future<void> refreshTasks() async {
    final current = _session;
    if (current == null) {
      return;
    }
    await _runBusy(() async {
      await _loadTasks(current.user.id, _selectedDate);
    });
  }

  Future<void> selectDate(DateTime date) async {
    final current = _session;
    _selectedDate = _dateOnly(date);
    notifyListeners();
    if (current == null) {
      return;
    }
    await _runBusy(() async {
      await _loadTasks(current.user.id, _selectedDate);
    });
  }

  Future<void> _loadTasks(int userId, DateTime date) async {
    final start = _dateOnly(date);
    final end = start.add(const Duration(days: 1));
    final today = _dateOnly(DateTime.now());
    final todayEnd = today.add(const Duration(days: 1));
    final service = TaskService(_timelineClient);
    final selectedTasks =
        service.listTasks(userId: userId, start: start, end: end);
    final todayTasks = start.isAtSameMomentAs(today)
        ? selectedTasks
        : service.listTasks(userId: userId, start: today, end: todayEnd);
    final loaded = await Future.wait<dynamic>([
      selectedTasks,
      todayTasks,
      service.listCourses(userId: userId, date: date),
      TodoService(_agentClient).listTodos(userId: userId),
      TodoService(_agentClient).listTodoHistory(userId: userId),
    ]);
    _tasks = loaded[0] as List<TaskItem>;
    _todayTasks = loaded[1] as List<TaskItem>;
    _courses = loaded[2] as List<CourseItem>;
    _todos = loaded[3] as List<TodoItem>;
    _todoHistory = loaded[4] as List<TodoItem>;
    _tasks = [..._tasks]..sort((a, b) => a.startTime.compareTo(b.startTime));
    _todayTasks = [..._todayTasks]
      ..sort((a, b) => a.startTime.compareTo(b.startTime));
    notifyListeners();
  }

  Future<void> refreshTodoHistory() async {
    final current = _session;
    if (current == null) {
      return;
    }
    await _runBusy(() async {
      _todoHistory = await TodoService(_agentClient).listTodoHistory(
        userId: current.user.id,
      );
      notifyListeners();
    });
  }

  Future<TaskItem?> createTask({
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
      return null;
    }
    TaskItem? task;
    await _runBusy(() async {
      task = await TaskService(_timelineClient).createTask(
        userId: current.user.id,
        title: title,
        startTime: startTime,
        endTime: endTime,
        description: description,
        location: location,
        priority: priority,
        category: category,
      );
      await _loadTasks(current.user.id, _selectedDate);
    });
    return task;
  }

  Future<void> completeTask(TaskItem task) async {
    final current = _session;
    if (current == null) {
      return;
    }
    await _runBusy(() async {
      await TaskService(_timelineClient).updateStatus(
        userId: current.user.id,
        taskId: task.id,
        status: TaskStatus.completed,
      );
      await _loadTasks(current.user.id, _selectedDate);
    });
  }

  Future<void> deleteTask(TaskItem task) async {
    final current = _session;
    if (current == null) {
      return;
    }
    await _runBusy(() async {
      await TaskService(_timelineClient).deleteTask(
        userId: current.user.id,
        taskId: task.id,
      );
      await _loadTasks(current.user.id, _selectedDate);
    });
  }

  Future<void> updateTask({
    required TaskItem task,
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
      await TaskService(_timelineClient).updateTask(
        userId: current.user.id,
        taskId: task.id,
        title: title,
        startTime: startTime,
        endTime: endTime,
        description: description,
        location: location,
        priority: priority,
        category: category,
      );
      await _loadTasks(current.user.id, _selectedDate);
    });
  }

  Future<void> uploadTaskImage(TaskItem task, String filePath) async {
    final current = _session;
    if (current == null) {
      return;
    }
    await _runBusy(() async {
      await TaskService(_timelineClient).uploadTaskImage(
        userId: current.user.id,
        taskId: task.id,
        filePath: filePath,
      );
      await _loadTasks(current.user.id, _selectedDate);
    });
  }

  Future<void> updateCourse({
    required CourseItem course,
    required String courseName,
    String? teacher,
    String? location,
    int? startSection,
    int? endSection,
  }) async {
    final current = _session;
    if (current == null) {
      return;
    }
    await _runBusy(() async {
      await TaskService(_timelineClient).updateCourse(
        userId: current.user.id,
        course: course,
        courseName: courseName,
        teacher: teacher,
        location: location,
        startSection: startSection,
        endSection: endSection,
      );
      await _loadTasks(current.user.id, _selectedDate);
    });
  }

  Future<void> deleteCourse(CourseItem course) async {
    final current = _session;
    if (current == null) {
      return;
    }
    await _runBusy(() async {
      await TaskService(_timelineClient).deleteCourse(
        userId: current.user.id,
        courseId: course.id,
      );
      await _loadTasks(current.user.id, _selectedDate);
    });
  }

  Future<void> uploadCourseImage(CourseItem course, String filePath) async {
    final current = _session;
    if (current == null) {
      return;
    }
    await _runBusy(() async {
      await TaskService(_timelineClient).uploadCourseImage(
        userId: current.user.id,
        courseId: course.id,
        filePath: filePath,
      );
      await _loadTasks(current.user.id, _selectedDate);
    });
  }

  Future<void> completeTodo(TodoItem todo) async {
    final current = _session;
    if (current == null) {
      return;
    }
    await _runBusy(() async {
      await TodoService(_agentClient).completeTodo(
        userId: current.user.id,
        todoId: todo.id,
      );
      await _loadTasks(current.user.id, _selectedDate);
    });
  }

  Future<void> sendAgentMessage(String content) async {
    final current = _session;
    final trimmed = content.trim();
    if (current == null || trimmed.isEmpty) {
      return;
    }
    final userMessage = ChatMessage(role: 'user', content: trimmed);
    final history = _messages;
    _messages = [
      ..._messages,
      userMessage,
      const ChatMessage(role: 'assistant', content: ''),
    ];
    _agentNeedsConfirmation = false;
    _agentConfirmationStage = '';
    _agentThinking = true;
    notifyListeners();

    try {
      await _runBusy(() async {
        AgentChatResponse? finalResponse;
        final service = AgentService(_agentClient);
        await for (final event in service.sendMessageStream(
          userId: current.user.id,
          message: trimmed,
          sessionId: _agentSessionId,
          history: history,
        )) {
          if (event.isToken) {
            if (_agentThinking) {
              _agentThinking = false;
            }
            _appendAssistantToken(event.content);
          } else if (event.isDone) {
            finalResponse = event.response;
          } else if (event.isError) {
            throw StateError(event.error!);
          }
        }

        if (finalResponse == null) {
          throw StateError('连接已中断，请稍后重试');
        }

        final response = finalResponse;
        _agentSessionId = response.sessionId;
        await _persistSession();
        _agentNeedsConfirmation = response.needsConfirmation;
        _agentConfirmationStage = response.confirmationStage;
        if (_messages.isNotEmpty && !_messages.last.isUser) {
          _messages = [
            ..._messages.take(_messages.length - 1),
            ChatMessage(role: 'assistant', content: response.reply),
          ];
        }
        if (response.tasksCreated.isNotEmpty ||
            response.tasksUpdated.isNotEmpty ||
            response.actionsTaken.isNotEmpty) {
          await _loadTasks(current.user.id, _selectedDate);
        }
      });
    } catch (_) {
      _removeEmptyAssistantPlaceholder();
      rethrow;
    } finally {
      _agentThinking = false;
      notifyListeners();
    }
  }

  Future<void> _loadChatHistory(int userId) async {
    try {
      final loaded = await AgentService(_agentClient).listHistory(
        userId: userId,
        sessionId: _agentSessionId,
      );
      if (loaded.isNotEmpty) {
        _messages = loaded;
      }
    } catch (_) {
      _messages = const [
        ChatMessage(role: 'assistant', content: '我是林。今天的安排、提醒和冲突都可以交给我。'),
      ];
    }
  }

  Future<void> clearChatHistory() async {
    final current = _session;
    if (current == null) {
      return;
    }
    await AgentService(_agentClient).clearHistory(
      userId: current.user.id,
      sessionId: _agentSessionId,
    );
    _agentNeedsConfirmation = false;
    _agentConfirmationStage = '';
    _messages = const [
      ChatMessage(role: 'assistant', content: '我是林。今天的安排、提醒和冲突都可以交给我。'),
    ];
    notifyListeners();
  }

  Future<ScheduleImportResult> importScheduleFromUrl(String url) async {
    final current = _session;
    if (current == null) {
      throw StateError('请先登录');
    }
    ScheduleImportResult? result;
    await _runBusy(() async {
      result = await CrawlerService(_crawlerClient).importScheduleFromUrl(
        userId: current.user.id,
        url: url,
      );
      if (result!.imported) {
        await _loadTasks(current.user.id, _selectedDate);
      }
    });
    return result!;
  }

  Future<ScheduleImportResult> importScheduleFromHtml({
    required String html,
    String? sourceUrl,
  }) async {
    final current = _session;
    if (current == null) {
      throw StateError('请先登录');
    }
    ScheduleImportResult? result;
    await _runBusy(() async {
      result = await CrawlerService(_crawlerClient).importScheduleFromHtml(
        userId: current.user.id,
        html: html,
        sourceUrl: sourceUrl,
      );
      if (result!.imported) {
        await _loadTasks(current.user.id, _selectedDate);
      }
    });
    return result!;
  }

  void clearError() {
    _error = null;
    notifyListeners();
  }

  Future<void> _persistSession() async {
    final current = _session;
    if (current == null) {
      return;
    }
    await SessionStore().save(AuthSession(
      token: current.token,
      tokenType: current.tokenType,
      sessionId: _agentSessionId ?? current.sessionId,
      user: current.user,
    ));
  }

  void _appendAssistantToken(String token) {
    if (token.isEmpty) {
      return;
    }
    if (_messages.isEmpty || _messages.last.isUser) {
      _messages = [
        ..._messages,
        ChatMessage(role: 'assistant', content: token)
      ];
    } else {
      final last = _messages.last;
      _messages = [
        ..._messages.take(_messages.length - 1),
        ChatMessage(role: 'assistant', content: last.content + token),
      ];
    }
    notifyListeners();
  }

  void _removeEmptyAssistantPlaceholder() {
    if (_messages.isNotEmpty &&
        !_messages.last.isUser &&
        _messages.last.content.isEmpty) {
      _messages = _messages.take(_messages.length - 1).toList(growable: false);
      notifyListeners();
    }
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

  static DateTime _dateOnly(DateTime value) {
    return DateTime(value.year, value.month, value.day);
  }
}

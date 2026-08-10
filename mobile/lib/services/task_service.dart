import '../core/api/api_client.dart';
import '../models/task_item.dart';

class TaskService {
  TaskService(this.client);

  final ApiClient client;

  Future<List<TaskItem>> listTasks({
    required int userId,
    DateTime? start,
    DateTime? end,
  }) async {
    final data = await client.get(
      '/api/v1/tasks',
      query: {
        'user_id': userId.toString(),
        'start': start?.toIso8601String(),
        'end': end?.toIso8601String(),
        'page_size': '100',
      },
    ) as Map<String, dynamic>;
    final items = data['items'] as List<dynamic>? ?? const [];
    return items
        .whereType<Map<String, dynamic>>()
        .map(TaskItem.fromJson)
        .toList();
  }

  Future<TaskItem> createTask({
    required int userId,
    required String title,
    required DateTime startTime,
    required DateTime endTime,
    String? description,
    String? location,
    TaskPriority priority = TaskPriority.medium,
    TaskCategory category = TaskCategory.personal,
  }) async {
    final data = await client.post(
      '/api/v1/tasks',
      query: {'user_id': userId.toString()},
      body: {
        'title': title,
        'description': description?.isEmpty == true ? null : description,
        'start_time': startTime.toIso8601String(),
        'end_time': endTime.toIso8601String(),
        'priority': priorityToApi(priority),
        'location': location?.isEmpty == true ? null : location,
        'category': categoryToApi(category),
        'tags': <String>[],
      },
    ) as Map<String, dynamic>;
    return TaskItem.fromJson(data);
  }

  Future<TaskItem> updateStatus({
    required int taskId,
    required TaskStatus status,
  }) async {
    final data = await client.put(
      '/api/v1/tasks/$taskId',
      body: {'status': statusToApi(status)},
    ) as Map<String, dynamic>;
    return TaskItem.fromJson(data);
  }

  Future<void> deleteTask(int taskId) async {
    await client.delete('/api/v1/tasks/$taskId');
  }
}

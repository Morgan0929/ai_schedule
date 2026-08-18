import '../core/api/api_client.dart';
import '../core/utils/date_format.dart';
import '../models/course_item.dart';
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
    required int userId,
    required int taskId,
    required TaskStatus status,
  }) async {
    final data = await client.put(
      '/api/v1/tasks/$taskId',
      query: {'user_id': userId.toString()},
      body: {'status': statusToApi(status)},
    ) as Map<String, dynamic>;
    return TaskItem.fromJson(data);
  }

  Future<TaskItem> updateTask({
    required int userId,
    required int taskId,
    required String title,
    required DateTime startTime,
    required DateTime endTime,
    String? description,
    String? location,
    TaskPriority priority = TaskPriority.medium,
    TaskCategory category = TaskCategory.personal,
  }) async {
    final data = await client.put(
      '/api/v1/tasks/$taskId',
      query: {'user_id': userId.toString()},
      body: {
        'title': title,
        'description': description?.isEmpty == true ? null : description,
        'start_time': startTime.toIso8601String(),
        'end_time': endTime.toIso8601String(),
        'priority': priorityToApi(priority),
        'location': location?.isEmpty == true ? null : location,
        'category': categoryToApi(category),
      },
    ) as Map<String, dynamic>;
    return TaskItem.fromJson(data);
  }

  Future<void> deleteTask({required int userId, required int taskId}) async {
    await client.delete(
      '/api/v1/tasks/$taskId',
      query: {'user_id': userId.toString()},
    );
  }

  Future<TaskAttachment> uploadTaskImage({
    required int userId,
    required int taskId,
    required String filePath,
  }) async {
    final data = await client.uploadFile(
      '/api/v1/tasks/$taskId/images',
      query: {'user_id': userId.toString()},
      fieldName: 'file',
      filePath: filePath,
    ) as Map<String, dynamic>;
    return TaskAttachment.fromJson(data);
  }

  Future<List<CourseItem>> listCourses({
    required int userId,
    required DateTime date,
  }) async {
    final data = await client.get(
      '/api/v1/schedules',
      query: {'user_id': userId.toString(), 'date': formatDate(date)},
    ) as List<dynamic>;
    return data
        .whereType<Map<String, dynamic>>()
        .map(CourseItem.fromJson)
        .toList();
  }

  Future<CourseItem> updateCourse({
    required int userId,
    required CourseItem course,
    required String courseName,
    String? teacher,
    String? location,
    int? startSection,
    int? endSection,
  }) async {
    final data = await client.put(
      '/api/v1/schedules/${course.id}',
      query: {'user_id': userId.toString()},
      body: {
        'course_name': courseName,
        'teacher': teacher?.isEmpty == true ? null : teacher,
        'location': location?.isEmpty == true ? null : location,
        'start_section': startSection,
        'end_section': endSection,
      },
    ) as Map<String, dynamic>;
    return CourseItem.fromJson(data);
  }

  Future<void> deleteCourse({required int userId, required int courseId}) async {
    await client.delete(
      '/api/v1/schedules/$courseId',
      query: {'user_id': userId.toString()},
    );
  }

  Future<CourseAttachment> uploadCourseImage({
    required int userId,
    required int courseId,
    required String filePath,
  }) async {
    final data = await client.uploadFile(
      '/api/v1/schedules/$courseId/images',
      query: {'user_id': userId.toString()},
      fieldName: 'file',
      filePath: filePath,
    ) as Map<String, dynamic>;
    return CourseAttachment.fromJson(data);
  }
}

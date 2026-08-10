import '../core/utils/date_format.dart';

enum TaskPriority { high, medium, low }

enum TaskStatus { pending, inProgress, completed, cancelled }

enum TaskCategory { meeting, trip, personal, work }

class TaskItem {
  const TaskItem({
    required this.id,
    required this.userId,
    required this.title,
    required this.startTime,
    required this.endTime,
    this.description,
    this.priority = TaskPriority.medium,
    this.status = TaskStatus.pending,
    this.location,
    this.category = TaskCategory.personal,
    this.tags = const [],
  });

  final int id;
  final int userId;
  final String title;
  final String? description;
  final DateTime startTime;
  final DateTime endTime;
  final TaskPriority priority;
  final TaskStatus status;
  final String? location;
  final TaskCategory category;
  final List<String> tags;

  bool get isToday {
    final now = DateTime.now();
    return startTime.year == now.year &&
        startTime.month == now.month &&
        startTime.day == now.day;
  }

  String get timeLabel => formatDurationRange(startTime, endTime);

  factory TaskItem.fromJson(Map<String, dynamic> json) {
    return TaskItem(
      id: json['id'] as int,
      userId: json['user_id'] as int,
      title: json['title']?.toString() ?? '',
      description: json['description']?.toString(),
      startTime: DateTime.parse(json['start_time'].toString()),
      endTime: DateTime.parse(json['end_time'].toString()),
      priority: _priorityFromApi(json['priority']?.toString()),
      status: _statusFromApi(json['status']?.toString()),
      location: json['location']?.toString(),
      category: _categoryFromApi(json['category']?.toString()),
      tags: (json['tags'] as List<dynamic>? ?? const [])
          .map((item) => item.toString())
          .toList(),
    );
  }

  static TaskPriority _priorityFromApi(String? value) {
    switch (value) {
      case 'HIGH':
        return TaskPriority.high;
      case 'LOW':
        return TaskPriority.low;
      default:
        return TaskPriority.medium;
    }
  }

  static TaskStatus _statusFromApi(String? value) {
    switch (value) {
      case 'IN_PROGRESS':
        return TaskStatus.inProgress;
      case 'COMPLETED':
        return TaskStatus.completed;
      case 'CANCELLED':
        return TaskStatus.cancelled;
      default:
        return TaskStatus.pending;
    }
  }

  static TaskCategory _categoryFromApi(String? value) {
    switch (value) {
      case 'MEETING':
        return TaskCategory.meeting;
      case 'TRIP':
        return TaskCategory.trip;
      case 'WORK':
        return TaskCategory.work;
      default:
        return TaskCategory.personal;
    }
  }
}

String priorityToApi(TaskPriority priority) {
  switch (priority) {
    case TaskPriority.high:
      return 'HIGH';
    case TaskPriority.low:
      return 'LOW';
    case TaskPriority.medium:
      return 'MEDIUM';
  }
}

String categoryToApi(TaskCategory category) {
  switch (category) {
    case TaskCategory.meeting:
      return 'MEETING';
    case TaskCategory.trip:
      return 'TRIP';
    case TaskCategory.work:
      return 'WORK';
    case TaskCategory.personal:
      return 'PERSONAL';
  }
}

String statusToApi(TaskStatus status) {
  switch (status) {
    case TaskStatus.inProgress:
      return 'IN_PROGRESS';
    case TaskStatus.completed:
      return 'COMPLETED';
    case TaskStatus.cancelled:
      return 'CANCELLED';
    case TaskStatus.pending:
      return 'PENDING';
  }
}

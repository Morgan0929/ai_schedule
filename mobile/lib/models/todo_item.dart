class TodoItem {
  const TodoItem({
    required this.id,
    required this.title,
    this.note,
    this.priority = 'MEDIUM',
    this.status = 'ACTIVE',
    this.createdAt,
    this.updatedAt,
  });

  final int id;
  final String title;
  final String? note;
  final String priority;
  final String status;
  final String? createdAt;
  final String? updatedAt;

  factory TodoItem.fromJson(Map<String, dynamic> json) {
    return TodoItem(
      id: json['id'] as int,
      title: json['title']?.toString() ?? '',
      note: json['note']?.toString(),
      priority: json['priority']?.toString() ?? 'MEDIUM',
      status: json['status']?.toString() ?? 'ACTIVE',
      createdAt: json['created_at']?.toString(),
      updatedAt: json['updated_at']?.toString(),
    );
  }
}

import 'package:flutter/material.dart';

import '../models/task_item.dart';

class TaskCard extends StatelessWidget {
  const TaskCard({
    required this.task,
    this.onComplete,
    this.onDelete,
    super.key,
  });

  final TaskItem task;
  final VoidCallback? onComplete;
  final VoidCallback? onDelete;

  @override
  Widget build(BuildContext context) {
    final color = _priorityColor(context, task.priority);
    return Card(
      child: Padding(
        padding: const EdgeInsets.all(14),
        child: Row(
          crossAxisAlignment: CrossAxisAlignment.start,
          children: [
            Container(
              width: 4,
              height: 56,
              decoration: BoxDecoration(
                color: color,
                borderRadius: BorderRadius.circular(4),
              ),
            ),
            const SizedBox(width: 12),
            Expanded(
              child: Column(
                crossAxisAlignment: CrossAxisAlignment.start,
                children: [
                  Text(
                    task.title,
                    maxLines: 2,
                    overflow: TextOverflow.ellipsis,
                    style: Theme.of(context).textTheme.titleMedium?.copyWith(
                          fontWeight: FontWeight.w700,
                          decoration: task.status == TaskStatus.completed
                              ? TextDecoration.lineThrough
                              : null,
                        ),
                  ),
                  const SizedBox(height: 6),
                  Wrap(
                    runSpacing: 6,
                    spacing: 10,
                    children: [
                      _Meta(icon: Icons.schedule, text: task.timeLabel),
                      if (task.location != null && task.location!.isNotEmpty)
                        _Meta(icon: Icons.place_outlined, text: task.location!),
                    ],
                  ),
                  if (task.description != null && task.description!.isNotEmpty) ...[
                    const SizedBox(height: 8),
                    Text(
                      task.description!,
                      maxLines: 2,
                      overflow: TextOverflow.ellipsis,
                      style: Theme.of(context).textTheme.bodyMedium,
                    ),
                  ],
                ],
              ),
            ),
            PopupMenuButton<String>(
              tooltip: '任务操作',
              onSelected: (value) {
                if (value == 'complete') {
                  onComplete?.call();
                }
                if (value == 'delete') {
                  onDelete?.call();
                }
              },
              itemBuilder: (context) => [
                if (task.status != TaskStatus.completed)
                  const PopupMenuItem(
                    value: 'complete',
                    child: Text('标记完成'),
                  ),
                const PopupMenuItem(value: 'delete', child: Text('删除')),
              ],
            ),
          ],
        ),
      ),
    );
  }

  Color _priorityColor(BuildContext context, TaskPriority priority) {
    switch (priority) {
      case TaskPriority.high:
        return Theme.of(context).colorScheme.error;
      case TaskPriority.low:
        return const Color(0xFF5E7C93);
      case TaskPriority.medium:
        return Theme.of(context).colorScheme.primary;
    }
  }
}

class _Meta extends StatelessWidget {
  const _Meta({required this.icon, required this.text});

  final IconData icon;
  final String text;

  @override
  Widget build(BuildContext context) {
    return Row(
      mainAxisSize: MainAxisSize.min,
      children: [
        Icon(icon, size: 16, color: Theme.of(context).colorScheme.secondary),
        const SizedBox(width: 4),
        Text(text, style: Theme.of(context).textTheme.bodySmall),
      ],
    );
  }
}

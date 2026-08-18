import 'package:flutter/material.dart';
import 'package:image_picker/image_picker.dart';

import '../app_scope.dart';
import '../models/todo_item.dart';
import '../models/task_item.dart';
import '../widgets/app_snack_bar.dart';
import '../widgets/error_banner.dart';
import '../widgets/task_card.dart';
import 'tasks_screen.dart';

class DashboardScreen extends StatelessWidget {
  const DashboardScreen({super.key});

  @override
  Widget build(BuildContext context) {
    final state = AppScope.of(context);
    final user = state.session!.user;
    final todayTasks = state.todayTasks;
    final todos = state.todos;
    final pendingCount =
        todayTasks.where((task) => task.status != TaskStatus.completed).length +
            todos.length;

    return RefreshIndicator(
      onRefresh: state.refreshTasks,
      child: ListView(
        padding: const EdgeInsets.fromLTRB(16, 8, 16, 24),
        children: [
          const ErrorBanner(),
          Card(
            child: Padding(
              padding: const EdgeInsets.all(18),
              child: Column(
                crossAxisAlignment: CrossAxisAlignment.start,
                children: [
                  Text(
                    '${user.username}，今天有 $pendingCount 项待处理',
                    style: Theme.of(context).textTheme.titleLarge?.copyWith(
                          fontWeight: FontWeight.w800,
                        ),
                  ),
                  const SizedBox(height: 12),
                  Row(
                    children: [
                      _Metric(
                        label: '全部',
                        value: (todayTasks.length + todos.length).toString(),
                      ),
                      const SizedBox(width: 10),
                      _Metric(label: '待办', value: todos.length.toString()),
                      const SizedBox(width: 10),
                      _Metric(
                        label: '高优先级',
                        value: todayTasks
                            .where((task) => task.priority == TaskPriority.high)
                            .length
                            .toString(),
                      ),
                    ],
                  ),
                ],
              ),
            ),
          ),
          const SizedBox(height: 16),
          Row(
            children: [
              Expanded(
                child: Text(
                  '待办',
                  style: Theme.of(context).textTheme.titleMedium?.copyWith(
                        fontWeight: FontWeight.w800,
                      ),
                ),
              ),
              TextButton.icon(
                onPressed: state.busy ? null : () => _showTodoHistory(context),
                icon: const Icon(Icons.history, size: 18),
                label: const Text('历史记录'),
              ),
            ],
          ),
          const SizedBox(height: 10),
          if (state.busy && todos.isEmpty && todayTasks.isEmpty)
            const SizedBox.shrink()
          else if (todos.isEmpty)
            const _EmptyTodos()
          else
            ...todos.map(
              (todo) => Padding(
                padding: const EdgeInsets.only(bottom: 10),
                child: _TodoCard(
                  title: todo.title,
                  note: todo.note,
                  onDone: () => state.completeTodo(todo),
                ),
              ),
            ),
          const SizedBox(height: 16),
          Text(
            '今日安排',
            style: Theme.of(context).textTheme.titleMedium?.copyWith(
                  fontWeight: FontWeight.w800,
                ),
          ),
          const SizedBox(height: 10),
          if (state.busy && state.tasks.isEmpty)
            const Center(
                child: Padding(
              padding: EdgeInsets.all(32),
              child: CircularProgressIndicator(),
            ))
          else if (todayTasks.isEmpty)
            const _EmptyToday()
          else
            ...todayTasks.map(
              (task) => Padding(
                padding: const EdgeInsets.only(bottom: 10),
                child: TaskCard(
                  task: task,
                  mediaBaseUrl: state.config.timelineServiceUrl,
                  onEdit: () => _editTask(context, task),
                  onUploadImage: () => _uploadTaskImage(context, task),
                  onComplete: () => _completeTask(context, task),
                  onDelete: () => _confirmDeleteTask(context, task),
                ),
              ),
            ),
        ],
      ),
    );
  }

  Future<void> _showTodoHistory(BuildContext context) async {
    final state = AppScope.of(context);
    try {
      await state.refreshTodoHistory();
    } catch (_) {
      if (context.mounted) {
        ScaffoldMessenger.of(context).showSnackBar(
          SnackBar(content: Text(state.error ?? '加载待办历史失败')),
        );
        state.clearError();
      }
      return;
    }
    if (!context.mounted) {
      return;
    }
    await showModalBottomSheet<void>(
      context: context,
      showDragHandle: true,
      builder: (_) => const _TodoHistorySheet(),
    );
  }

  Future<void> _editTask(BuildContext context, TaskItem task) async {
    await showModalBottomSheet<void>(
      context: context,
      isScrollControlled: true,
      builder: (_) => TaskEditorSheet(
        initialDate: task.startTime,
        task: task,
      ),
    );
  }

  Future<void> _uploadTaskImage(BuildContext context, TaskItem task) async {
    final picker = ImagePicker();
    final image = await picker.pickImage(
      source: ImageSource.gallery,
      imageQuality: 88,
    );
    if (image == null) {
      return;
    }
    final state = AppScope.of(context);
    try {
      await state.uploadTaskImage(task, image.path);
      if (context.mounted) {
        showSuccessSnackBar(context, '图片已上传');
      }
    } catch (_) {
      if (context.mounted) {
        showErrorSnackBar(context, state.error ?? '上传图片失败');
        state.clearError();
      }
    }
  }

  Future<void> _completeTask(BuildContext context, TaskItem task) async {
    final state = AppScope.of(context);
    try {
      await state.completeTask(task);
      if (context.mounted) {
        showSuccessSnackBar(context, '已完成「${task.title}」');
      }
    } catch (_) {
      if (context.mounted) {
        showErrorSnackBar(context, state.error ?? '更新日程失败');
        state.clearError();
      }
    }
  }

  Future<void> _confirmDeleteTask(BuildContext context, TaskItem task) async {
    final state = AppScope.of(context);
    final confirmed = await showDialog<bool>(
      context: context,
      builder: (context) => AlertDialog(
        title: const Text('删除日程'),
        content: Text('确定删除「${task.title}」吗？'),
        actions: [
          TextButton(
            onPressed: () => Navigator.of(context).pop(false),
            child: const Text('取消'),
          ),
          FilledButton(
            onPressed: () => Navigator.of(context).pop(true),
            child: const Text('删除'),
          ),
        ],
      ),
    );
    if (confirmed != true) {
      return;
    }
    try {
      await state.deleteTask(task);
      if (context.mounted) {
        showSuccessSnackBar(context, '已删除「${task.title}」');
      }
    } catch (_) {
      if (context.mounted) {
        showErrorSnackBar(context, state.error ?? '删除日程失败');
        state.clearError();
      }
    }
  }
}

class _TodoHistorySheet extends StatelessWidget {
  const _TodoHistorySheet();

  @override
  Widget build(BuildContext context) {
    final history = AppScope.of(context).todoHistory;
    return SafeArea(
      child: Padding(
        padding: const EdgeInsets.fromLTRB(16, 0, 16, 16),
        child: Column(
          mainAxisSize: MainAxisSize.min,
          crossAxisAlignment: CrossAxisAlignment.start,
          children: [
            Text(
              '待办历史',
              style: Theme.of(context).textTheme.titleLarge?.copyWith(
                    fontWeight: FontWeight.w800,
                  ),
            ),
            const SizedBox(height: 12),
            if (history.isEmpty)
              const Padding(
                padding: EdgeInsets.symmetric(vertical: 32),
                child: Center(child: Text('暂无历史记录。')),
              )
            else
              Flexible(
                child: ListView.separated(
                  shrinkWrap: true,
                  itemCount: history.length,
                  separatorBuilder: (_, __) => const Divider(height: 1),
                  itemBuilder: (context, index) {
                    final todo = history[index];
                    return ListTile(
                      contentPadding: EdgeInsets.zero,
                      leading: Icon(
                        todo.status == 'DONE'
                            ? Icons.task_alt
                            : Icons.archive_outlined,
                      ),
                      title: Text(todo.title),
                      subtitle: Text(_historySubtitle(todo)),
                      trailing: _StatusChip(status: todo.status),
                    );
                  },
                ),
              ),
          ],
        ),
      ),
    );
  }

  String _historySubtitle(TodoItem todo) {
    final date = todo.updatedAt ?? todo.createdAt ?? '';
    final note = todo.note?.isNotEmpty == true ? ' · ${todo.note}' : '';
    return date.isEmpty ? note.replaceFirst(' · ', '') : '$date$note';
  }
}

class _StatusChip extends StatelessWidget {
  const _StatusChip({required this.status});

  final String status;

  @override
  Widget build(BuildContext context) {
    final isDone = status == 'DONE';
    final colors = Theme.of(context).colorScheme;
    return Chip(
      label: Text(isDone ? '已完成' : '已归档'),
      visualDensity: VisualDensity.compact,
      backgroundColor:
          isDone ? colors.primaryContainer : colors.surfaceContainerHighest,
      labelStyle: TextStyle(
        color: isDone ? colors.onPrimaryContainer : colors.onSurfaceVariant,
      ),
    );
  }
}

class _TodoCard extends StatelessWidget {
  const _TodoCard({required this.title, this.note, required this.onDone});

  final String title;
  final String? note;
  final VoidCallback onDone;

  @override
  Widget build(BuildContext context) {
    return Card(
      child: Padding(
        padding: const EdgeInsets.all(14),
        child: Row(
          children: [
            Icon(Icons.checklist, color: Theme.of(context).colorScheme.primary),
            const SizedBox(width: 12),
            Expanded(
              child: Column(
                crossAxisAlignment: CrossAxisAlignment.start,
                children: [
                  Text(
                    title,
                    maxLines: 2,
                    overflow: TextOverflow.ellipsis,
                    style: Theme.of(context).textTheme.titleMedium?.copyWith(
                          fontWeight: FontWeight.w700,
                        ),
                  ),
                  if (note != null && note!.isNotEmpty) ...[
                    const SizedBox(height: 4),
                    Text(
                      note!,
                      maxLines: 2,
                      overflow: TextOverflow.ellipsis,
                      style: Theme.of(context).textTheme.bodySmall,
                    ),
                  ],
                ],
              ),
            ),
            IconButton(
              tooltip: '完成',
              onPressed: onDone,
              icon: const Icon(Icons.done),
            ),
          ],
        ),
      ),
    );
  }
}

class _EmptyTodos extends StatelessWidget {
  const _EmptyTodos();

  @override
  Widget build(BuildContext context) {
    return Card(
      child: Padding(
        padding: const EdgeInsets.all(18),
        child: Row(
          children: [
            Icon(Icons.task_alt, color: Theme.of(context).colorScheme.primary),
            const SizedBox(width: 12),
            const Expanded(child: Text('暂无待办。')),
          ],
        ),
      ),
    );
  }
}

class _Metric extends StatelessWidget {
  const _Metric({required this.label, required this.value});

  final String label;
  final String value;

  @override
  Widget build(BuildContext context) {
    return Expanded(
      child: Container(
        padding: const EdgeInsets.all(12),
        decoration: BoxDecoration(
          color: Theme.of(context).colorScheme.surfaceContainerHighest,
          borderRadius: BorderRadius.circular(8),
        ),
        child: Column(
          crossAxisAlignment: CrossAxisAlignment.start,
          children: [
            Text(label, style: Theme.of(context).textTheme.bodySmall),
            const SizedBox(height: 6),
            Text(
              value,
              style: Theme.of(context).textTheme.headlineSmall?.copyWith(
                    fontWeight: FontWeight.w800,
                  ),
            ),
          ],
        ),
      ),
    );
  }
}

class _EmptyToday extends StatelessWidget {
  const _EmptyToday();

  @override
  Widget build(BuildContext context) {
    return Card(
      child: Padding(
        padding: const EdgeInsets.all(24),
        child: Row(
          children: [
            Icon(Icons.event_available,
                color: Theme.of(context).colorScheme.primary),
            const SizedBox(width: 12),
            const Expanded(child: Text('今天暂无安排。')),
          ],
        ),
      ),
    );
  }
}

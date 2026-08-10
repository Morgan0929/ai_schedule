import 'package:flutter/material.dart';

import '../app_scope.dart';
import '../core/utils/date_format.dart';
import '../models/task_item.dart';
import '../widgets/error_banner.dart';
import '../widgets/task_card.dart';

class TasksScreen extends StatelessWidget {
  const TasksScreen({super.key});

  @override
  Widget build(BuildContext context) {
    final state = AppScope.of(context);
    final tasks = state.tasks;

    return Scaffold(
      body: RefreshIndicator(
        onRefresh: state.refreshTasks,
        child: ListView(
          padding: const EdgeInsets.fromLTRB(16, 8, 16, 88),
          children: [
            const ErrorBanner(),
            Row(
              children: [
                Expanded(
                  child: Text(
                    '全部日程',
                    style: Theme.of(context).textTheme.titleMedium?.copyWith(
                          fontWeight: FontWeight.w800,
                        ),
                  ),
                ),
                Text('${tasks.length} 项'),
              ],
            ),
            const SizedBox(height: 12),
            if (state.busy && tasks.isEmpty)
              const Center(
                child: Padding(
                  padding: EdgeInsets.all(32),
                  child: CircularProgressIndicator(),
                ),
              )
            else if (tasks.isEmpty)
              const _EmptyTasks()
            else
              ...tasks.map(
                (task) => Padding(
                  padding: const EdgeInsets.only(bottom: 10),
                  child: TaskCard(
                    task: task,
                    onComplete: () => state.completeTask(task),
                    onDelete: () => _confirmDelete(context, task),
                  ),
                ),
              ),
          ],
        ),
      ),
      floatingActionButton: FloatingActionButton.extended(
        onPressed: () => showModalBottomSheet<void>(
          context: context,
          isScrollControlled: true,
          builder: (_) => const _CreateTaskSheet(),
        ),
        icon: const Icon(Icons.add),
        label: const Text('新建'),
      ),
    );
  }

  Future<void> _confirmDelete(BuildContext context, TaskItem task) async {
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
    if (confirmed == true) {
      await state.deleteTask(task);
    }
  }
}

class _CreateTaskSheet extends StatefulWidget {
  const _CreateTaskSheet();

  @override
  State<_CreateTaskSheet> createState() => _CreateTaskSheetState();
}

class _CreateTaskSheetState extends State<_CreateTaskSheet> {
  final _formKey = GlobalKey<FormState>();
  final _titleController = TextEditingController();
  final _descriptionController = TextEditingController();
  final _locationController = TextEditingController();
  DateTime _start = DateTime.now().add(const Duration(hours: 1));
  DateTime _end = DateTime.now().add(const Duration(hours: 2));
  TaskPriority _priority = TaskPriority.medium;
  TaskCategory _category = TaskCategory.personal;

  @override
  void dispose() {
    _titleController.dispose();
    _descriptionController.dispose();
    _locationController.dispose();
    super.dispose();
  }

  @override
  Widget build(BuildContext context) {
    final bottom = MediaQuery.of(context).viewInsets.bottom;
    return Padding(
      padding: EdgeInsets.fromLTRB(16, 16, 16, bottom + 16),
      child: Form(
        key: _formKey,
        child: SingleChildScrollView(
          child: Column(
            mainAxisSize: MainAxisSize.min,
            crossAxisAlignment: CrossAxisAlignment.stretch,
            children: [
              Row(
                children: [
                  Expanded(
                    child: Text(
                      '新建日程',
                      style: Theme.of(context).textTheme.titleLarge?.copyWith(
                            fontWeight: FontWeight.w800,
                          ),
                    ),
                  ),
                  IconButton(
                    tooltip: '关闭',
                    onPressed: () => Navigator.of(context).pop(),
                    icon: const Icon(Icons.close),
                  ),
                ],
              ),
              const SizedBox(height: 12),
              TextFormField(
                controller: _titleController,
                decoration: const InputDecoration(
                  labelText: '标题',
                  prefixIcon: Icon(Icons.event_note),
                ),
                validator: (value) =>
                    value == null || value.trim().isEmpty ? '请输入标题' : null,
              ),
              const SizedBox(height: 12),
              TextFormField(
                controller: _descriptionController,
                maxLines: 2,
                decoration: const InputDecoration(
                  labelText: '备注',
                  prefixIcon: Icon(Icons.notes),
                ),
              ),
              const SizedBox(height: 12),
              TextFormField(
                controller: _locationController,
                decoration: const InputDecoration(
                  labelText: '地点',
                  prefixIcon: Icon(Icons.place_outlined),
                ),
              ),
              const SizedBox(height: 12),
              Row(
                children: [
                  Expanded(
                    child: OutlinedButton.icon(
                      onPressed: () => _pickDateTime(isStart: true),
                      icon: const Icon(Icons.play_arrow),
                      label: Text(formatDateTime(_start)),
                    ),
                  ),
                ],
              ),
              const SizedBox(height: 8),
              Row(
                children: [
                  Expanded(
                    child: OutlinedButton.icon(
                      onPressed: () => _pickDateTime(isStart: false),
                      icon: const Icon(Icons.stop),
                      label: Text(formatDateTime(_end)),
                    ),
                  ),
                ],
              ),
              const SizedBox(height: 12),
              SegmentedButton<TaskPriority>(
                segments: const [
                  ButtonSegment(value: TaskPriority.high, label: Text('高')),
                  ButtonSegment(value: TaskPriority.medium, label: Text('中')),
                  ButtonSegment(value: TaskPriority.low, label: Text('低')),
                ],
                selected: {_priority},
                onSelectionChanged: (value) => setState(() => _priority = value.first),
              ),
              const SizedBox(height: 12),
              DropdownButtonFormField<TaskCategory>(
                value: _category,
                decoration: const InputDecoration(
                  labelText: '类型',
                  prefixIcon: Icon(Icons.category_outlined),
                ),
                items: const [
                  DropdownMenuItem(value: TaskCategory.personal, child: Text('个人')),
                  DropdownMenuItem(value: TaskCategory.work, child: Text('工作')),
                  DropdownMenuItem(value: TaskCategory.meeting, child: Text('会议')),
                  DropdownMenuItem(value: TaskCategory.trip, child: Text('出行')),
                ],
                onChanged: (value) {
                  if (value != null) {
                    setState(() => _category = value);
                  }
                },
              ),
              const SizedBox(height: 16),
              FilledButton.icon(
                onPressed: _submit,
                icon: const Icon(Icons.check),
                label: const Text('保存'),
              ),
            ],
          ),
        ),
      ),
    );
  }

  Future<void> _pickDateTime({required bool isStart}) async {
    final current = isStart ? _start : _end;
    final date = await showDatePicker(
      context: context,
      initialDate: current,
      firstDate: DateTime.now().subtract(const Duration(days: 365)),
      lastDate: DateTime.now().add(const Duration(days: 365 * 2)),
    );
    if (date == null || !mounted) {
      return;
    }
    final time = await showTimePicker(
      context: context,
      initialTime: TimeOfDay.fromDateTime(current),
    );
    if (time == null) {
      return;
    }
    final selected = DateTime(date.year, date.month, date.day, time.hour, time.minute);
    setState(() {
      if (isStart) {
        _start = selected;
        if (!_end.isAfter(_start)) {
          _end = _start.add(const Duration(hours: 1));
        }
      } else {
        _end = selected;
      }
    });
  }

  Future<void> _submit() async {
    if (!_formKey.currentState!.validate()) {
      return;
    }
    if (!_end.isAfter(_start)) {
      ScaffoldMessenger.of(context).showSnackBar(
        const SnackBar(content: Text('结束时间必须晚于开始时间')),
      );
      return;
    }
    final state = AppScope.of(context);
    try {
      await state.createTask(
        title: _titleController.text.trim(),
        description: _descriptionController.text.trim(),
        location: _locationController.text.trim(),
        startTime: _start,
        endTime: _end,
        priority: _priority,
        category: _category,
      );
      if (mounted) {
        Navigator.of(context).pop();
      }
    } catch (_) {
      if (mounted) {
        ScaffoldMessenger.of(context).showSnackBar(
          SnackBar(content: Text(state.error ?? '创建失败')),
        );
      }
    }
  }
}

class _EmptyTasks extends StatelessWidget {
  const _EmptyTasks();

  @override
  Widget build(BuildContext context) {
    return Card(
      child: Padding(
        padding: const EdgeInsets.all(24),
        child: Row(
          children: [
            Icon(Icons.inbox_outlined, color: Theme.of(context).colorScheme.primary),
            const SizedBox(width: 12),
            const Expanded(child: Text('还没有日程。')),
          ],
        ),
      ),
    );
  }
}

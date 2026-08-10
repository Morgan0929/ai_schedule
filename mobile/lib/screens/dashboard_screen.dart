import 'package:flutter/material.dart';

import '../app_scope.dart';
import '../models/task_item.dart';
import '../widgets/error_banner.dart';
import '../widgets/task_card.dart';

class DashboardScreen extends StatelessWidget {
  const DashboardScreen({super.key});

  @override
  Widget build(BuildContext context) {
    final state = AppScope.of(context);
    final user = state.session!.user;
    final todayTasks = state.tasks.where((task) => task.isToday).toList();
    final pendingCount = todayTasks
        .where((task) => task.status != TaskStatus.completed)
        .length;

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
                      _Metric(label: '全部', value: todayTasks.length.toString()),
                      const SizedBox(width: 10),
                      _Metric(label: '待办', value: pendingCount.toString()),
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
          Text(
            '今日安排',
            style: Theme.of(context).textTheme.titleMedium?.copyWith(
                  fontWeight: FontWeight.w800,
                ),
          ),
          const SizedBox(height: 10),
          if (state.busy && state.tasks.isEmpty)
            const Center(child: Padding(
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
                  onComplete: () => state.completeTask(task),
                  onDelete: () => state.deleteTask(task),
                ),
              ),
            ),
        ],
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
            Icon(Icons.event_available, color: Theme.of(context).colorScheme.primary),
            const SizedBox(width: 12),
            const Expanded(child: Text('今天暂无安排。')),
          ],
        ),
      ),
    );
  }
}

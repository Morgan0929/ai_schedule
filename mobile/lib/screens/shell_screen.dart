import 'package:flutter/material.dart';

import '../app_scope.dart';
import 'agent_screen.dart';
import 'dashboard_screen.dart';
import 'tasks_screen.dart';

class ShellScreen extends StatefulWidget {
  const ShellScreen({super.key});

  @override
  State<ShellScreen> createState() => _ShellScreenState();
}

class _ShellScreenState extends State<ShellScreen> {
  int _index = 0;

  @override
  Widget build(BuildContext context) {
    final state = AppScope.of(context);
    return Scaffold(
      appBar: AppBar(
        title: Text(_title),
        actions: [
          TextButton(
            onPressed: state.busy ? null : state.refreshTasks,
            child: const Text('刷新'),
          ),
          TextButton(
            onPressed: state.signOut,
            child: const Text('退出'),
          ),
        ],
      ),
      body: _LazyTabHost(
        index: _index,
        builder: _buildScreen,
      ),
      bottomNavigationBar: NavigationBar(
        selectedIndex: _index,
        onDestinationSelected: (value) => setState(() => _index = value),
        destinations: const [
          NavigationDestination(icon: Icon(Icons.today_outlined), label: '今日'),
          NavigationDestination(icon: Icon(Icons.event_note_outlined), label: '日程'),
          NavigationDestination(icon: Icon(Icons.auto_awesome_outlined), label: '林'),
        ],
      ),
    );
  }

  String get _title {
    switch (_index) {
      case 1:
        return '日程';
      case 2:
        return '林';
      default:
        return '今日';
    }
  }

  Widget _buildScreen(int index) {
    switch (index) {
      case 1:
        return const TasksScreen();
      case 2:
        return const AgentScreen();
      default:
        return const DashboardScreen();
    }
  }
}

class _LazyTabHost extends StatefulWidget {
  const _LazyTabHost({required this.index, required this.builder});

  final int index;
  final Widget Function(int index) builder;

  @override
  State<_LazyTabHost> createState() => _LazyTabHostState();
}

class _LazyTabHostState extends State<_LazyTabHost> {
  final Map<int, Widget> _cache = {};

  @override
  Widget build(BuildContext context) {
    _cache.putIfAbsent(widget.index, () => widget.builder(widget.index));
    return Stack(
      children: _cache.entries
          .map(
            (entry) => _IndexedTabView(
              isActive: entry.key == widget.index,
              child: entry.value,
            ),
          )
          .toList(growable: false),
    );
  }
}

class _IndexedTabView extends StatelessWidget {
  const _IndexedTabView({required this.isActive, required this.child});

  final bool isActive;
  final Widget child;

  @override
  Widget build(BuildContext context) {
    return Offstage(
      offstage: !isActive,
      child: TickerMode(
        enabled: isActive,
        child: child,
      ),
    );
  }
}

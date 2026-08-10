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

  final _screens = const [
    DashboardScreen(),
    TasksScreen(),
    AgentScreen(),
  ];

  @override
  Widget build(BuildContext context) {
    final state = AppScope.of(context);
    return Scaffold(
      appBar: AppBar(
        title: Text(_title),
        actions: [
          IconButton(
            tooltip: '刷新',
            onPressed: state.busy ? null : state.refreshTasks,
            icon: const Icon(Icons.refresh),
          ),
          IconButton(
            tooltip: '退出登录',
            onPressed: state.signOut,
            icon: const Icon(Icons.logout),
          ),
        ],
      ),
      body: IndexedStack(index: _index, children: _screens),
      bottomNavigationBar: NavigationBar(
        selectedIndex: _index,
        onDestinationSelected: (value) => setState(() => _index = value),
        destinations: const [
          NavigationDestination(icon: Icon(Icons.today_outlined), label: '今日'),
          NavigationDestination(icon: Icon(Icons.list_alt), label: '日程'),
          NavigationDestination(icon: Icon(Icons.auto_awesome), label: '林'),
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
}

import 'package:flutter/material.dart';

import 'state/app_state.dart';

class AppScope extends InheritedNotifier<AppState> {
  const AppScope({
    required super.notifier,
    required super.child,
    super.key,
  });

  static AppState of(BuildContext context) {
    final scope = context.dependOnInheritedWidgetOfExactType<AppScope>();
    assert(scope != null, 'AppScope not found in widget tree');
    return scope!.notifier!;
  }
}

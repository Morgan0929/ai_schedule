import 'package:flutter/material.dart';

import 'app_scope.dart';
import 'screens/login_screen.dart';
import 'screens/shell_screen.dart';
import 'state/app_state.dart';

void main() {
  runApp(const LinApp());
}

class LinApp extends StatefulWidget {
  const LinApp({super.key});

  @override
  State<LinApp> createState() => _LinAppState();
}

class _LinAppState extends State<LinApp> {
  late final AppState appState;

  @override
  void initState() {
    super.initState();
    appState = AppState();
  }

  @override
  void dispose() {
    appState.dispose();
    super.dispose();
  }

  @override
  Widget build(BuildContext context) {
    return AppScope(
      notifier: appState,
      child: MaterialApp(
        title: '林',
        debugShowCheckedModeBanner: false,
        theme: ThemeData(
          useMaterial3: true,
          colorScheme: ColorScheme.fromSeed(
            seedColor: const Color(0xFF246B5F),
            brightness: Brightness.light,
          ),
          scaffoldBackgroundColor: const Color(0xFFF6F7F8),
          cardTheme: const CardThemeData(
            elevation: 0,
            margin: EdgeInsets.zero,
            shape: RoundedRectangleBorder(
              borderRadius: BorderRadius.all(Radius.circular(8)),
              side: BorderSide(color: Color(0xFFE1E5E8)),
            ),
          ),
          inputDecorationTheme: const InputDecorationTheme(
            border: OutlineInputBorder(
              borderRadius: BorderRadius.all(Radius.circular(8)),
            ),
          ),
        ),
        home: const _HomeGate(),
      ),
    );
  }
}

class _HomeGate extends StatelessWidget {
  const _HomeGate();

  @override
  Widget build(BuildContext context) {
    final state = AppScope.of(context);
    return state.isSignedIn ? const ShellScreen() : const LoginScreen();
  }
}

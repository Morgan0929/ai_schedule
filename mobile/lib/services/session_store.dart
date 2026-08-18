import 'dart:convert';

import 'package:shared_preferences/shared_preferences.dart';

import '../models/auth_session.dart';

class SessionStore {
  static const _key = 'auth_session';

  Future<AuthSession?> read() async {
    final preferences = await SharedPreferences.getInstance();
    final raw = preferences.getString(_key);
    if (raw == null || raw.isEmpty) {
      return null;
    }
    try {
      final value = jsonDecode(raw);
      if (value is! Map<String, dynamic>) {
        await clear();
        return null;
      }
      final session = AuthSession.fromJson(value);
      if (session.token.isEmpty || session.user.id <= 0) {
        await clear();
        return null;
      }
      return session;
    } catch (_) {
      await clear();
      return null;
    }
  }

  Future<void> save(AuthSession session) async {
    final preferences = await SharedPreferences.getInstance();
    await preferences.setString(_key, jsonEncode(session.toJson()));
  }

  Future<void> clear() async {
    final preferences = await SharedPreferences.getInstance();
    await preferences.remove(_key);
  }
}

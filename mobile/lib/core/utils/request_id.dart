import 'dart:math';

/// One ID per user action. Keep it when retrying an uncertain result.
String newRequestId() {
  final random = Random.secure();
  return List.generate(16, (_) => random.nextInt(256).toRadixString(16).padLeft(2, '0')).join();
}

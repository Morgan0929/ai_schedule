import 'package:flutter_test/flutter_test.dart';

import 'package:ai_schedule_mobile/main.dart';

void main() {
  testWidgets('shows login screen on launch', (tester) async {
    await tester.pumpWidget(const LinApp());

    expect(find.text('林'), findsOneWidget);
    expect(find.text('个人事务秘书'), findsOneWidget);
    expect(find.text('进入'), findsOneWidget);
  });
}

import 'package:flutter/widgets.dart';
import 'package:flutter_test/flutter_test.dart';

import 'package:fixpro/main.dart';
import 'package:fixpro/screens/dashboard_screen.dart';

void main() {
  testWidgets('Welcome screen shows title and CTA', (tester) async {
    await tester.pumpWidget(const FixProApp());

    expect(find.textContaining('Bienvenue sur FixPro'), findsOneWidget);
    expect(find.text('Commencer maintenant'), findsOneWidget);
    expect(find.text('Se connecter'), findsOneWidget);
  });

  testWidgets('Tapping "Commencer maintenant" opens the dashboard',
      (tester) async {
    await tester.pumpWidget(const FixProApp());

    await tester.tap(find.text('Commencer maintenant'));
    await tester.pumpAndSettle();

    expect(find.byType(DashboardScreen), findsOneWidget);
    expect(find.text('Bonjour Mamadou 👋'), findsOneWidget);
    expect(find.textContaining('Trouver un technicien'), findsOneWidget);
  });

  testWidgets('Opening a technician shows the detail screen', (tester) async {
    await tester.pumpWidget(const FixProApp());
    await tester.tap(find.text('Commencer maintenant'));
    await tester.pumpAndSettle();

    final tech = find.text('Ibrahima Bah');
    await tester.scrollUntilVisible(
      tech,
      250,
      scrollable: find.byType(Scrollable).first,
    );
    await tester.pumpAndSettle();
    await tester.tap(tech);
    await tester.pumpAndSettle();

    expect(find.text('Profil du technicien'), findsOneWidget);
    expect(find.text('Réserver maintenant'), findsOneWidget);
    expect(find.text('À propos'), findsOneWidget);
  });
}

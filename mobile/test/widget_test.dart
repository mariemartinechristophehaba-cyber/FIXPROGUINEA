import 'package:flutter/material.dart';
import 'package:flutter_test/flutter_test.dart';

import 'package:fixpro/main.dart';
import 'package:fixpro/screens/auth_screen.dart';
import 'package:fixpro/screens/dashboard_screen.dart';
import 'package:fixpro/theme/app_theme.dart';

Widget _wrap(Widget child) =>
    MaterialApp(theme: AppTheme.dark, home: child);

void main() {
  testWidgets('Welcome screen shows title and CTA', (tester) async {
    await tester.pumpWidget(const FixProApp());

    expect(find.textContaining('Bienvenue sur FixPro'), findsOneWidget);
    expect(find.text('Commencer maintenant'), findsOneWidget);
    expect(find.text('Se connecter'), findsOneWidget);
  });

  testWidgets('Tapping "Commencer maintenant" opens the sign-up screen',
      (tester) async {
    await tester.pumpWidget(const FixProApp());

    await tester.tap(find.text('Commencer maintenant'));
    await tester.pumpAndSettle();

    expect(find.byType(AuthScreen), findsOneWidget);
    expect(find.text('Créer un compte'), findsOneWidget);
    expect(find.text('Prénom'), findsOneWidget);
    expect(find.text('Numéro de téléphone'), findsOneWidget);
  });

  testWidgets('Tapping "Se connecter" opens the login screen', (tester) async {
    await tester.pumpWidget(const FixProApp());

    await tester.tap(find.text('Se connecter'));
    await tester.pumpAndSettle();

    expect(find.byType(AuthScreen), findsOneWidget);
    expect(find.textContaining('Bon retour'), findsOneWidget);
  });

  testWidgets('Dashboard renders greeting and technicians', (tester) async {
    await tester.pumpWidget(_wrap(const DashboardScreen()));
    await tester.pumpAndSettle();

    expect(find.textContaining('Bonjour'), findsOneWidget);
    expect(find.textContaining('Trouver un technicien'), findsOneWidget);
  });

  testWidgets('Opening a technician shows the detail screen', (tester) async {
    await tester.pumpWidget(_wrap(const DashboardScreen()));
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

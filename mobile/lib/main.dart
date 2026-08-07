import 'package:flutter/material.dart';

import 'screens/dashboard_screen.dart';
import 'screens/welcome_screen.dart';
import 'services/auth_service.dart';
import 'services/supabase_service.dart';
import 'theme/app_colors.dart';
import 'theme/app_theme.dart';

Future<void> main() async {
  WidgetsFlutterBinding.ensureInitialized();
  await SupabaseService.initialize();
  runApp(const FixProApp());
}

/// Application FixPro — mise en relation artisans/clients en Guinée.
class FixProApp extends StatelessWidget {
  const FixProApp({super.key});

  @override
  Widget build(BuildContext context) {
    return MaterialApp(
      title: 'FixPro',
      debugShowCheckedModeBanner: false,
      theme: AppTheme.dark,
      home: const AuthGate(),
      builder: (context, child) => _MobileFrame(child: child),
    );
  }
}

/// Décide de l'écran de départ : tableau de bord si une session Supabase
/// est déjà active, sinon écran de bienvenue.
class AuthGate extends StatelessWidget {
  const AuthGate({super.key});

  @override
  Widget build(BuildContext context) {
    const auth = AuthService();
    if (auth.isLoggedIn) return const DashboardScreen();
    return const WelcomeScreen();
  }
}

/// Contraint le contenu à une largeur "mobile" et le centre sur les grands
/// écrans (web / tablette) pour préserver le rendu conçu pour téléphone.
class _MobileFrame extends StatelessWidget {
  const _MobileFrame({required this.child});

  final Widget? child;

  @override
  Widget build(BuildContext context) {
    if (child == null) return const SizedBox.shrink();
    return ColoredBox(
      color: AppColors.background,
      child: Center(
        child: ConstrainedBox(
          constraints: const BoxConstraints(maxWidth: 460),
          child: child,
        ),
      ),
    );
  }
}

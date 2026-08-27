import 'package:flutter/material.dart';

import '../services/api_service.dart';
import '../theme/app_colors.dart';
import '../widgets/common.dart';
import '../widgets/glass_card.dart';
import 'technician_dashboard_screen.dart';
import 'technician_signup_screen.dart';

/// Ecran de connexion reserve au technicien (session FixPro Flask).
class TechnicianAuthScreen extends StatefulWidget {
  const TechnicianAuthScreen({super.key});

  @override
  State<TechnicianAuthScreen> createState() => _TechnicianAuthScreenState();
}

class _TechnicianAuthScreenState extends State<TechnicianAuthScreen> {
  final _phone = TextEditingController();
  final _password = TextEditingController();
  bool _loading = false;
  String? _error;

  Future<void> _login() async {
    setState(() {
      _error = null;
      _loading = true;
    });
    try {
      await ApiService.login(
        phone: _phone.text.trim(),
        password: _password.text.trim(),
      );
      if (!mounted) return;
      Navigator.of(context).pushAndRemoveUntil(
        MaterialPageRoute(builder: (_) => const TechnicianDashboardScreen()),
        (route) => false,
      );
    } on ApiFailure catch (e) {
      setState(() => _error = e.message);
    } finally {
      if (mounted) setState(() => _loading = false);
    }
  }

  @override
  Widget build(BuildContext context) {
    final textTheme = Theme.of(context).textTheme;
    return Scaffold(
      body: DecoratedBox(
        decoration: const BoxDecoration(gradient: AppColors.backgroundGradient),
        child: SafeArea(
          child: Padding(
            padding: const EdgeInsets.symmetric(horizontal: 24),
            child: Column(
              crossAxisAlignment: CrossAxisAlignment.start,
              children: [
                const SizedBox(height: 40),
                Text(
                  'Espace technicien',
                  style: textTheme.headlineLarge?.copyWith(fontSize: 28),
                ),
                const SizedBox(height: 8),
                Text(
                  'Connectez-vous avec vos identifiants FixPro.',
                  style: textTheme.bodyMedium?.copyWith(
                    color: AppColors.lightGrey,
                    fontSize: 14,
                    height: 1.4,
                  ),
                ),
                const SizedBox(height: 32),
                GlassCard(
                  padding: const EdgeInsets.all(20),
                  radius: 24,
                  child: Column(
                    children: [
                      _Field(label: 'Telephone', controller: _phone),
                      const SizedBox(height: 16),
                      _Field(
                        label: 'Mot de passe',
                        controller: _password,
                        obscure: true,
                      ),
                      if (_error != null) ...[
                        const SizedBox(height: 14),
                        Text(
                          _error!,
                          style: const TextStyle(
                            color: AppColors.red,
                            fontSize: 13,
                          ),
                          textAlign: TextAlign.center,
                        ),
                      ],
                      const SizedBox(height: 20),
                      GradientButton(
                        label: _loading ? 'Connexion...' : 'Se connecter',
                        gradient: AppColors.orangeGradient,
                        onPressed: _loading ? null : _login,
                        height: 52,
                      ),
                      const SizedBox(height: 16),
                      TextButton(
                        onPressed: () {
                          Navigator.of(context).push(
                            MaterialPageRoute(builder: (_) => const TechnicianSignupScreen()),
                          );
                        },
                        child: const Text(
                          "S'inscrire en tant que technicien",
                          style: TextStyle(color: AppColors.lightGrey),
                        ),
                      ),
                    ],
                  ),
                ),
              ],
            ),
          ),
        ),
      ),
    );
  }
}

class _Field extends StatelessWidget {
  const _Field({
    required this.label,
    required this.controller,
    this.obscure = false,
  });

  final String label;
  final TextEditingController controller;
  final bool obscure;

  @override
  Widget build(BuildContext context) {
    return TextField(
      controller: controller,
      obscureText: obscure,
      style: const TextStyle(color: AppColors.white),
      cursorColor: AppColors.orange,
      decoration: InputDecoration(
        isDense: true,
        filled: true,
        fillColor: AppColors.background.withOpacity( 0.55),
        hintText: label,
        hintStyle: const TextStyle(color: AppColors.lightGrey, fontSize: 14),
        contentPadding: const EdgeInsets.symmetric(vertical: 14, horizontal: 16),
        border: OutlineInputBorder(
          borderRadius: BorderRadius.circular(16),
          borderSide: BorderSide.none,
        ),
      ),
    );
  }
}

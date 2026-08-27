import 'package:flutter/material.dart';

import '../services/api_service.dart';
import '../theme/app_colors.dart';
import '../widgets/common.dart';
import '../widgets/glass_card.dart';

/// Ecran d'inscription d'un technicien depuis l'application mobile.
class TechnicianSignupScreen extends StatefulWidget {
  const TechnicianSignupScreen({super.key});

  @override
  State<TechnicianSignupScreen> createState() => _TechnicianSignupScreenState();
}

class _TechnicianSignupScreenState extends State<TechnicianSignupScreen> {
  final _firstName = TextEditingController();
  final _lastName = TextEditingController();
  final _phone = TextEditingController();
  final _email = TextEditingController();
  final _profession = TextEditingController();
  final _city = TextEditingController();
  final _quartier = TextEditingController();
  final _bio = TextEditingController();
  final _password = TextEditingController();
  final _confirmPassword = TextEditingController();

  bool _loading = false;
  String? _error;

  Future<void> _submit() async {
    setState(() {
      _error = null;
      _loading = true;
    });

    if (_password.text.trim() != _confirmPassword.text.trim()) {
      setState(() {
        _error = "Les mots de passe ne correspondent pas.";
        _loading = false;
      });
      return;
    }

    try {
      await ApiService.registerTechnician(
        firstName: _firstName.text.trim(),
        lastName: _lastName.text.trim(),
        phone: _phone.text.trim(),
        password: _password.text.trim(),
        email: _email.text.trim(),
        profession: _profession.text.trim(),
        city: _city.text.trim(),
        quartier: _quartier.text.trim(),
        bio: _bio.text.trim(),
      );
      if (!mounted) return;
      await showDialog(
        context: context,
        builder: (_) => AlertDialog(
          backgroundColor: AppColors.background,
          title: const Text("Inscription envoyee"),
          content: const Text(
              "Votre demande a ete envoyee. Un administrateur va l'etudier."),
          actions: [
            TextButton(
              onPressed: () => Navigator.of(context).pop(),
              child: const Text("OK"),
            ),
          ],
        ),
      );
      if (mounted) Navigator.of(context).pop();
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
          child: SingleChildScrollView(
            padding: const EdgeInsets.symmetric(horizontal: 24, vertical: 32),
            child: Column(
              crossAxisAlignment: CrossAxisAlignment.start,
              children: [
                Text(
                  "Inscription technicien",
                  style: textTheme.headlineLarge?.copyWith(fontSize: 28),
                ),
                const SizedBox(height: 8),
                Text(
                  "Remplissez ce formulaire. Votre compte sera active apres validation.",
                  style: textTheme.bodyMedium?.copyWith(
                    color: AppColors.lightGrey,
                    fontSize: 14,
                    height: 1.4,
                  ),
                ),
                const SizedBox(height: 24),
                GlassCard(
                  padding: const EdgeInsets.all(20),
                  radius: 24,
                  child: Column(
                    children: [
                      _Field(label: 'Prenom', controller: _firstName),
                      const SizedBox(height: 12),
                      _Field(label: 'Nom', controller: _lastName),
                      const SizedBox(height: 12),
                      _Field(label: 'Telephone', controller: _phone),
                      const SizedBox(height: 12),
                      _Field(label: 'Email (optionnel)', controller: _email),
                      const SizedBox(height: 12),
                      _Field(label: 'Metier', controller: _profession),
                      const SizedBox(height: 12),
                      _Field(label: 'Ville', controller: _city),
                      const SizedBox(height: 12),
                      _Field(label: 'Quartier', controller: _quartier),
                      const SizedBox(height: 12),
                      _Field(label: 'Bio (optionnel)', controller: _bio),
                      const SizedBox(height: 12),
                      _Field(
                        label: 'Mot de passe',
                        controller: _password,
                        obscure: true,
                      ),
                      const SizedBox(height: 12),
                      _Field(
                        label: 'Confirmer le mot de passe',
                        controller: _confirmPassword,
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
                        label: _loading ? 'Envoi...' : "S'inscrire",
                        gradient: AppColors.orangeGradient,
                        onPressed: _loading ? null : _submit,
                        height: 52,
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
        fillColor: AppColors.background.withOpacity(0.55),
        hintText: label,
        hintStyle: const TextStyle(color: AppColors.lightGrey, fontSize: 14),
        contentPadding:
            const EdgeInsets.symmetric(vertical: 14, horizontal: 16),
        border: OutlineInputBorder(
          borderRadius: BorderRadius.circular(16),
          borderSide: BorderSide.none,
        ),
      ),
    );
  }
}

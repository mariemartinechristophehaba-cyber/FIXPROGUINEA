import 'package:flutter/material.dart';

import '../theme/app_colors.dart';
import '../widgets/common.dart';
import 'auth_screen.dart';

/// Écran de bienvenue : logo, titre, description et actions d'entrée.
class WelcomeScreen extends StatelessWidget {
  const WelcomeScreen({super.key});

  void _openAuth(BuildContext context, {required bool signUp}) {
    Navigator.of(context).push(
      MaterialPageRoute(builder: (_) => AuthScreen(startInSignUp: signUp)),
    );
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
              children: [
                const Spacer(flex: 2),
                const _FixProLogo(),
                const SizedBox(height: 40),
                Text(
                  '👋 Bienvenue sur FixPro !',
                  textAlign: TextAlign.center,
                  style: textTheme.headlineLarge?.copyWith(fontSize: 30),
                ),
                const SizedBox(height: 18),
                Text(
                  'La plateforme qui connecte les Guinéens avec les meilleurs '
                  'techniciens — plombiers, électriciens, frigoristes, maçons '
                  'et bien plus encore.',
                  textAlign: TextAlign.center,
                  style: textTheme.bodyMedium?.copyWith(
                    fontSize: 15,
                    height: 1.5,
                    color: AppColors.lightGrey,
                  ),
                ),
                const Spacer(flex: 3),
                GradientButton(
                  label: 'Commencer maintenant',
                  gradient: AppColors.orangeGradient,
                  trailingIcon: Icons.arrow_forward_rounded,
                  onPressed: () => _openAuth(context, signUp: true),
                ),
                const SizedBox(height: 20),
                Text(
                  'Déjà un compte ?',
                  style: textTheme.bodyMedium?.copyWith(
                    color: AppColors.lightGrey,
                    fontSize: 14,
                  ),
                ),
                const SizedBox(height: 12),
                _SecondaryButton(
                  label: 'Se connecter',
                  onPressed: () => _openAuth(context, signUp: false),
                ),
                const Spacer(flex: 1),
              ],
            ),
          ),
        ),
      ),
    );
  }
}

/// Logo FixPro : badge à dégradé + nom en deux couleurs.
class _FixProLogo extends StatelessWidget {
  const _FixProLogo();

  @override
  Widget build(BuildContext context) {
    return Column(
      children: [
        Container(
          width: 96,
          height: 96,
          decoration: BoxDecoration(
            gradient: AppColors.blueGradient,
            borderRadius: BorderRadius.circular(28),
            boxShadow: [
              BoxShadow(
                color: AppColors.primaryBlue.withValues(alpha: 0.45),
                blurRadius: 30,
                offset: const Offset(0, 12),
              ),
            ],
          ),
          child: const Icon(Icons.handyman_rounded,
              color: AppColors.white, size: 48),
        ),
        const SizedBox(height: 20),
        RichText(
          text: const TextSpan(
            style: TextStyle(
              fontSize: 30,
              fontWeight: FontWeight.w900,
              letterSpacing: -0.5,
            ),
            children: [
              TextSpan(text: 'Fix', style: TextStyle(color: AppColors.white)),
              TextSpan(text: 'Pro', style: TextStyle(color: AppColors.orange)),
            ],
          ),
        ),
      ],
    );
  }
}

/// Bouton secondaire "outline" premium.
class _SecondaryButton extends StatelessWidget {
  const _SecondaryButton({required this.label, required this.onPressed});

  final String label;
  final VoidCallback onPressed;

  @override
  Widget build(BuildContext context) {
    final borderRadius = BorderRadius.circular(18);
    return Material(
      color: AppColors.white.withValues(alpha: 0.06),
      borderRadius: borderRadius,
      child: InkWell(
        borderRadius: borderRadius,
        onTap: onPressed,
        child: Container(
          height: 54,
          width: double.infinity,
          alignment: Alignment.center,
          decoration: BoxDecoration(
            borderRadius: borderRadius,
            border: Border.all(color: AppColors.primaryBlue, width: 1.4),
          ),
          child: const Text(
            'Se connecter',
            style: TextStyle(
              color: AppColors.white,
              fontWeight: FontWeight.w700,
              fontSize: 16,
            ),
          ),
        ),
      ),
    );
  }
}

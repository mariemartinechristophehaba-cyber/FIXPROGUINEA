import 'package:flutter/material.dart';

import '../theme/app_colors.dart';
import '../widgets/common.dart';
import 'auth_screen.dart';
import 'technician_auth_screen.dart';

/// Ecran de bienvenue : logo, titre, description et actions d'entree.
class WelcomeScreen extends StatelessWidget {
  const WelcomeScreen({super.key});

  void _openAuth(BuildContext context, {required bool signUp}) {
    Navigator.of(context).push(
      MaterialPageRoute(builder: (_) => AuthScreen(startInSignUp: signUp)),
    );
  }

  void _openTechnician(BuildContext context) {
    Navigator.of(context).push(
      MaterialPageRoute(builder: (_) => const TechnicianAuthScreen()),
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
                  'Bienvenue sur FixPro !',
                  textAlign: TextAlign.center,
                  style: textTheme.headlineLarge?.copyWith(fontSize: 30),
                ),
                const SizedBox(height: 18),
                Text(
                  'La plateforme qui connecte les Guineens avec les meilleurs '
                  'techniciens - plombiers, electriciens, frigoristes, macons '
                  'et bien plus encore.',
                  textAlign: TextAlign.center,
                  style: textTheme.bodyMedium?.copyWith(
                    fontSize: 15,
                    height: 1.5,
                    color: AppColors.lightGrey,
                  ),
                ),
                const Spacer(flex: 2),
                GradientButton(
                  label: 'Commencer maintenant',
                  gradient: AppColors.orangeGradient,
                  trailingIcon: Icons.arrow_forward_rounded,
                  onPressed: () => _openAuth(context, signUp: true),
                ),
                const SizedBox(height: 20),
                Text(
                  'Deja un compte ?',
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
                const SizedBox(height: 18),
                Text(
                  'Vous etes technicien ?',
                  style: textTheme.bodyMedium?.copyWith(
                    color: AppColors.lightGrey,
                    fontSize: 14,
                  ),
                ),
                const SizedBox(height: 12),
                _SecondaryButton(
                  label: 'Espace technicien',
                  onPressed: () => _openTechnician(context),
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

/// Bouton secondaire transparent avec bordure blanche.
class _SecondaryButton extends StatelessWidget {
  final String label;
  final VoidCallback onPressed;

  const _SecondaryButton({required this.label, required this.onPressed});

  @override
  Widget build(BuildContext context) {
    return SizedBox(
      width: double.infinity,
      child: OutlinedButton(
        onPressed: onPressed,
        style: OutlinedButton.styleFrom(
          foregroundColor: AppColors.white,
          side: const BorderSide(color: AppColors.white),
          padding: const EdgeInsets.symmetric(vertical: 16),
          shape: RoundedRectangleBorder(
            borderRadius: BorderRadius.circular(12),
          ),
        ),
        child: Text(label),
      ),
    );
  }
}

/// Logo FixPro : badge a degrade + nom en deux couleurs.
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
                color: AppColors.primaryBlue.withOpacity( 0.45),
                blurRadius: 30,
                offset: const Offset(0, 12),
              ),
            ],
          ),
          child: const Icon(Icons.handyman_rounded,
              color: AppColors.white, size: 48),
        ),
        const SizedBox(height: 16),
        Row(
          mainAxisAlignment: MainAxisAlignment.center,
          children: [
            Text(
              'Fix',
              style: Theme.of(context)
                  .textTheme
                  .headlineLarge
                  ?.copyWith(fontSize: 36),
            ),
            Text(
              'Pro',
              style: Theme.of(context)
                  .textTheme
                  .headlineLarge
                  ?.copyWith(fontSize: 36, color: AppColors.orange),
            ),
          ],
        ),
      ],
    );
  }
}

import 'package:flutter/material.dart';

import '../services/auth_service.dart';
import '../theme/app_colors.dart';
import '../widgets/common.dart';
import 'dashboard_screen.dart';

/// Écran d'authentification : bascule entre Connexion et Inscription.
class AuthScreen extends StatefulWidget {
  const AuthScreen({super.key, this.startInSignUp = false});

  final bool startInSignUp;

  @override
  State<AuthScreen> createState() => _AuthScreenState();
}

class _AuthScreenState extends State<AuthScreen> {
  final _authService = const AuthService();
  final _formKey = GlobalKey<FormState>();
  final _nameCtrl = TextEditingController();
  final _emailCtrl = TextEditingController();
  final _passwordCtrl = TextEditingController();

  late bool _isSignUp = widget.startInSignUp;
  bool _loading = false;
  bool _obscure = true;
  String? _error;
  String? _info;

  @override
  void dispose() {
    _nameCtrl.dispose();
    _emailCtrl.dispose();
    _passwordCtrl.dispose();
    super.dispose();
  }

  void _toggleMode() {
    setState(() {
      _isSignUp = !_isSignUp;
      _error = null;
      _info = null;
    });
  }

  Future<void> _submit() async {
    if (!_formKey.currentState!.validate()) return;
    setState(() {
      _loading = true;
      _error = null;
      _info = null;
    });
    try {
      if (_isSignUp) {
        final outcome = await _authService.signUp(
          email: _emailCtrl.text,
          password: _passwordCtrl.text,
          fullName: _nameCtrl.text,
        );
        if (!mounted) return;
        if (outcome.needsEmailConfirmation) {
          setState(() {
            _isSignUp = false;
            _info = 'Compte créé ! Confirme ton e-mail puis connecte-toi.';
          });
        } else {
          _goToDashboard();
        }
      } else {
        await _authService.signIn(
          email: _emailCtrl.text,
          password: _passwordCtrl.text,
        );
        if (!mounted) return;
        _goToDashboard();
      }
    } on AuthFailure catch (e) {
      if (mounted) setState(() => _error = e.message);
    } catch (_) {
      if (mounted) {
        setState(() => _error = 'Une erreur est survenue. Réessaie.');
      }
    } finally {
      if (mounted) setState(() => _loading = false);
    }
  }

  void _goToDashboard() {
    Navigator.of(context).pushReplacement(
      MaterialPageRoute(builder: (_) => const DashboardScreen()),
    );
  }

  @override
  Widget build(BuildContext context) {
    final textTheme = Theme.of(context).textTheme;
    return Scaffold(
      body: DecoratedBox(
        decoration: const BoxDecoration(gradient: AppColors.backgroundGradient),
        child: SafeArea(
          child: SingleChildScrollView(
            padding: const EdgeInsets.fromLTRB(24, 12, 24, 32),
            child: Column(
              crossAxisAlignment: CrossAxisAlignment.stretch,
              children: [
                Align(
                  alignment: Alignment.centerLeft,
                  child: IconButton(
                    onPressed: () => Navigator.of(context).maybePop(),
                    icon: const Icon(Icons.arrow_back_rounded,
                        color: AppColors.white),
                  ),
                ),
                const SizedBox(height: 8),
                const _AuthLogo(),
                const SizedBox(height: 28),
                Text(
                  _isSignUp ? 'Créer un compte' : 'Bon retour 👋',
                  textAlign: TextAlign.center,
                  style: textTheme.headlineLarge?.copyWith(fontSize: 26),
                ),
                const SizedBox(height: 8),
                Text(
                  _isSignUp
                      ? 'Inscris-toi pour trouver un technicien.'
                      : 'Connecte-toi pour accéder à ton espace.',
                  textAlign: TextAlign.center,
                  style: textTheme.bodyMedium
                      ?.copyWith(color: AppColors.lightGrey, fontSize: 14),
                ),
                const SizedBox(height: 28),
                Form(
                  key: _formKey,
                  child: Column(
                    children: [
                      if (_isSignUp) ...[
                        _Field(
                          controller: _nameCtrl,
                          label: 'Nom complet',
                          icon: Icons.person_outline_rounded,
                          textInputAction: TextInputAction.next,
                          validator: (v) => (v == null || v.trim().isEmpty)
                              ? 'Entre ton nom'
                              : null,
                        ),
                        const SizedBox(height: 14),
                      ],
                      _Field(
                        controller: _emailCtrl,
                        label: 'E-mail',
                        icon: Icons.mail_outline_rounded,
                        keyboardType: TextInputType.emailAddress,
                        textInputAction: TextInputAction.next,
                        validator: (v) {
                          final value = (v ?? '').trim();
                          if (value.isEmpty) return 'Entre ton e-mail';
                          if (!value.contains('@') || !value.contains('.')) {
                            return 'E-mail invalide';
                          }
                          return null;
                        },
                      ),
                      const SizedBox(height: 14),
                      _Field(
                        controller: _passwordCtrl,
                        label: 'Mot de passe',
                        icon: Icons.lock_outline_rounded,
                        obscure: _obscure,
                        textInputAction: TextInputAction.done,
                        onSubmitted: (_) => _submit(),
                        suffix: IconButton(
                          onPressed: () =>
                              setState(() => _obscure = !_obscure),
                          icon: Icon(
                            _obscure
                                ? Icons.visibility_outlined
                                : Icons.visibility_off_outlined,
                            color: AppColors.lightGrey,
                            size: 20,
                          ),
                        ),
                        validator: (v) => (v == null || v.length < 6)
                            ? '6 caractères minimum'
                            : null,
                      ),
                    ],
                  ),
                ),
                if (_error != null) ...[
                  const SizedBox(height: 16),
                  _Banner(message: _error!, color: AppColors.red),
                ],
                if (_info != null) ...[
                  const SizedBox(height: 16),
                  _Banner(message: _info!, color: AppColors.green),
                ],
                const SizedBox(height: 24),
                GradientButton(
                  label: _isSignUp ? "S'inscrire" : 'Se connecter',
                  gradient: AppColors.orangeGradient,
                  loading: _loading,
                  onPressed: _loading ? null : _submit,
                ),
                const SizedBox(height: 18),
                Wrap(
                  alignment: WrapAlignment.center,
                  crossAxisAlignment: WrapCrossAlignment.center,
                  children: [
                    Text(
                      _isSignUp ? 'Déjà un compte ?' : 'Pas encore de compte ?',
                      style: const TextStyle(
                          color: AppColors.lightGrey, fontSize: 14),
                    ),
                    TextButton(
                      onPressed: _loading ? null : _toggleMode,
                      child: Text(
                        _isSignUp ? 'Se connecter' : "S'inscrire",
                        style: const TextStyle(
                          color: AppColors.orange,
                          fontWeight: FontWeight.w700,
                          fontSize: 14,
                        ),
                      ),
                    ),
                  ],
                ),
              ],
            ),
          ),
        ),
      ),
    );
  }
}

class _AuthLogo extends StatelessWidget {
  const _AuthLogo();

  @override
  Widget build(BuildContext context) {
    return Column(
      children: [
        Container(
          width: 72,
          height: 72,
          decoration: BoxDecoration(
            gradient: AppColors.blueGradient,
            borderRadius: BorderRadius.circular(22),
            boxShadow: [
              BoxShadow(
                color: AppColors.primaryBlue.withValues(alpha: 0.4),
                blurRadius: 24,
                offset: const Offset(0, 10),
              ),
            ],
          ),
          child: const Icon(Icons.handyman_rounded,
              color: AppColors.white, size: 36),
        ),
      ],
    );
  }
}

class _Field extends StatelessWidget {
  const _Field({
    required this.controller,
    required this.label,
    required this.icon,
    this.validator,
    this.keyboardType,
    this.textInputAction,
    this.obscure = false,
    this.suffix,
    this.onSubmitted,
  });

  final TextEditingController controller;
  final String label;
  final IconData icon;
  final String? Function(String?)? validator;
  final TextInputType? keyboardType;
  final TextInputAction? textInputAction;
  final bool obscure;
  final Widget? suffix;
  final ValueChanged<String>? onSubmitted;

  @override
  Widget build(BuildContext context) {
    return TextFormField(
      controller: controller,
      validator: validator,
      keyboardType: keyboardType,
      textInputAction: textInputAction,
      obscureText: obscure,
      onFieldSubmitted: onSubmitted,
      style: const TextStyle(color: AppColors.white),
      decoration: InputDecoration(
        labelText: label,
        labelStyle: const TextStyle(color: AppColors.lightGrey),
        prefixIcon: Icon(icon, color: AppColors.lightGrey, size: 20),
        suffixIcon: suffix,
        filled: true,
        fillColor: AppColors.card,
        enabledBorder: OutlineInputBorder(
          borderRadius: BorderRadius.circular(16),
          borderSide: const BorderSide(color: AppColors.glassBorder),
        ),
        focusedBorder: OutlineInputBorder(
          borderRadius: BorderRadius.circular(16),
          borderSide: const BorderSide(color: AppColors.primaryBlue, width: 1.4),
        ),
        errorBorder: OutlineInputBorder(
          borderRadius: BorderRadius.circular(16),
          borderSide: const BorderSide(color: AppColors.red),
        ),
        focusedErrorBorder: OutlineInputBorder(
          borderRadius: BorderRadius.circular(16),
          borderSide: const BorderSide(color: AppColors.red, width: 1.4),
        ),
      ),
    );
  }
}

class _Banner extends StatelessWidget {
  const _Banner({required this.message, required this.color});

  final String message;
  final Color color;

  @override
  Widget build(BuildContext context) {
    return Container(
      padding: const EdgeInsets.symmetric(horizontal: 14, vertical: 12),
      decoration: BoxDecoration(
        color: color.withValues(alpha: 0.14),
        borderRadius: BorderRadius.circular(14),
        border: Border.all(color: color.withValues(alpha: 0.5)),
      ),
      child: Text(
        message,
        style: TextStyle(color: color, fontSize: 13.5, height: 1.35),
      ),
    );
  }
}

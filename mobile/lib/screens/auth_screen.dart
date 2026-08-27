import 'package:flutter/material.dart';
import 'package:flutter/services.dart';

import '../services/auth_service.dart';
import '../theme/app_colors.dart';
import '../widgets/common.dart';
import 'dashboard_screen.dart';

/// Écran d'authentification par téléphone + code : bascule Connexion /
/// Inscription. Pas d'e-mail visible pour l'utilisateur.
class AuthScreen extends StatefulWidget {
  const AuthScreen({super.key, this.startInSignUp = false});

  final bool startInSignUp;

  @override
  State<AuthScreen> createState() => _AuthScreenState();
}

class _AuthScreenState extends State<AuthScreen> {
  static const String _countryCode = '224';

  final _authService = const AuthService();
  final _formKey = GlobalKey<FormState>();
  final _firstNameCtrl = TextEditingController();
  final _lastNameCtrl = TextEditingController();
  final _phoneCtrl = TextEditingController();
  final _codeCtrl = TextEditingController();

  late bool _isSignUp = widget.startInSignUp;
  bool _loading = false;
  bool _googleLoading = false;
  bool _obscure = true;
  String? _error;

  @override
  void dispose() {
    _firstNameCtrl.dispose();
    _lastNameCtrl.dispose();
    _phoneCtrl.dispose();
    _codeCtrl.dispose();
    super.dispose();
  }

  void _toggleMode() {
    setState(() {
      _isSignUp = !_isSignUp;
      _error = null;
    });
  }

  Future<void> _googleSignIn() async {
    setState(() {
      _googleLoading = true;
      _error = null;
    });
    try {
      // Sur le web, redirige vers Google puis recharge l'app (AuthGate gère
      // la suite). Sur mobile, la session revient via le callback.
      await _authService.signInWithGoogle();
    } on AuthFailure catch (e) {
      if (mounted) {
        setState(() {
          _error = e.message;
          _googleLoading = false;
        });
      }
    } catch (_) {
      if (mounted) {
        setState(() {
          _error = 'Connexion Google impossible. Réessaie.';
          _googleLoading = false;
        });
      }
    }
  }

  Future<void> _submit() async {
    if (!_formKey.currentState!.validate()) return;
    setState(() {
      _loading = true;
      _error = null;
    });
    try {
      if (_isSignUp) {
        await _authService.signUp(
          phone: '$_countryCode${_phoneCtrl.text}',
          code: _codeCtrl.text,
          firstName: _firstNameCtrl.text,
          lastName: _lastNameCtrl.text,
        );
      } else {
        await _authService.signIn(
          phone: '$_countryCode${_phoneCtrl.text}',
          code: _codeCtrl.text,
        );
      }
      if (!mounted) return;
      Navigator.of(context).pushReplacement(
        MaterialPageRoute(builder: (_) => const DashboardScreen()),
      );
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
                      ? 'Inscris-toi avec Google ou ton numéro.'
                      : 'Connecte-toi avec Google ou ton numéro.',
                  textAlign: TextAlign.center,
                  style: textTheme.bodyMedium
                      ?.copyWith(color: AppColors.lightGrey, fontSize: 14),
                ),
                const SizedBox(height: 28),
                _GoogleButton(
                  loading: _googleLoading,
                  onPressed:
                      (_loading || _googleLoading) ? null : _googleSignIn,
                ),
                const SizedBox(height: 20),
                Row(
                  children: [
                    const Expanded(child: Divider(color: AppColors.glassBorder)),
                    Padding(
                      padding: const EdgeInsets.symmetric(horizontal: 12),
                      child: Text('ou',
                          style: textTheme.bodyMedium
                              ?.copyWith(color: AppColors.lightGrey)),
                    ),
                    const Expanded(child: Divider(color: AppColors.glassBorder)),
                  ],
                ),
                const SizedBox(height: 20),
                Form(
                  key: _formKey,
                  child: Column(
                    children: [
                      if (_isSignUp) ...[
                        _Field(
                          controller: _firstNameCtrl,
                          label: 'Prénom',
                          icon: Icons.person_outline_rounded,
                          textInputAction: TextInputAction.next,
                          validator: (v) => (v == null || v.trim().isEmpty)
                              ? 'Entre ton prénom'
                              : null,
                        ),
                        const SizedBox(height: 14),
                        _Field(
                          controller: _lastNameCtrl,
                          label: 'Nom',
                          icon: Icons.badge_outlined,
                          textInputAction: TextInputAction.next,
                          validator: (v) => (v == null || v.trim().isEmpty)
                              ? 'Entre ton nom'
                              : null,
                        ),
                        const SizedBox(height: 14),
                      ],
                      _Field(
                        controller: _phoneCtrl,
                        label: 'Numéro de téléphone',
                        icon: Icons.phone_outlined,
                        prefixText: '+$_countryCode ',
                        keyboardType: TextInputType.phone,
                        textInputAction: TextInputAction.next,
                        inputFormatters: [
                          FilteringTextInputFormatter.digitsOnly,
                        ],
                        validator: (v) {
                          final digits = AuthService.normalizePhone(v ?? '');
                          if (digits.isEmpty) return 'Entre ton numéro';
                          if (digits.length < 8) return 'Numéro trop court';
                          return null;
                        },
                      ),
                      const SizedBox(height: 14),
                      _Field(
                        controller: _codeCtrl,
                        label: 'Code (6 chiffres min.)',
                        icon: Icons.lock_outline_rounded,
                        obscure: _obscure,
                        keyboardType: TextInputType.number,
                        textInputAction: TextInputAction.done,
                        onSubmitted: (_) => _submit(),
                        inputFormatters: [
                          FilteringTextInputFormatter.digitsOnly,
                        ],
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
                            ? '6 chiffres minimum'
                            : null,
                      ),
                    ],
                  ),
                ),
                if (_error != null) ...[
                  const SizedBox(height: 16),
                  _Banner(message: _error!, color: AppColors.red),
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
                color: AppColors.primaryBlue.withOpacity( 0.4),
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

class _GoogleButton extends StatelessWidget {
  const _GoogleButton({required this.onPressed, this.loading = false});

  final VoidCallback? onPressed;
  final bool loading;

  @override
  Widget build(BuildContext context) {
    return SizedBox(
      height: 54,
      child: OutlinedButton(
        onPressed: onPressed,
        style: OutlinedButton.styleFrom(
          backgroundColor: AppColors.white,
          foregroundColor: const Color(0xFF1F1F1F),
          disabledBackgroundColor: AppColors.white.withOpacity( 0.7),
          shape: RoundedRectangleBorder(
            borderRadius: BorderRadius.circular(16),
          ),
          side: BorderSide.none,
        ),
        child: loading
            ? const SizedBox(
                width: 22,
                height: 22,
                child: CircularProgressIndicator(
                    strokeWidth: 2.4, color: Color(0xFF1F1F1F)),
              )
            : Row(
                mainAxisAlignment: MainAxisAlignment.center,
                children: const [
                  _GoogleLogo(),
                  SizedBox(width: 12),
                  Text(
                    'Continuer avec Google',
                    style: TextStyle(
                      fontSize: 15.5,
                      fontWeight: FontWeight.w600,
                      color: Color(0xFF1F1F1F),
                    ),
                  ),
                ],
              ),
      ),
    );
  }
}

/// Logo Google « G » multicolore dessiné sans asset externe.
class _GoogleLogo extends StatelessWidget {
  const _GoogleLogo();

  @override
  Widget build(BuildContext context) {
    return Container(
      width: 20,
      height: 20,
      alignment: Alignment.center,
      decoration: const BoxDecoration(
        shape: BoxShape.circle,
        gradient: SweepGradient(
          colors: [
            Color(0xFF4285F4),
            Color(0xFF34A853),
            Color(0xFFFBBC05),
            Color(0xFFEA4335),
            Color(0xFF4285F4),
          ],
        ),
      ),
      child: Container(
        width: 8,
        height: 8,
        decoration: const BoxDecoration(
          color: AppColors.white,
          shape: BoxShape.circle,
        ),
        child: const Center(
          child: Text(
            'G',
            style: TextStyle(
              fontSize: 11,
              height: 1.0,
              fontWeight: FontWeight.w800,
              color: Color(0xFF4285F4),
            ),
          ),
        ),
      ),
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
    this.inputFormatters,
    this.prefixText,
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
  final List<TextInputFormatter>? inputFormatters;
  final String? prefixText;

  @override
  Widget build(BuildContext context) {
    return TextFormField(
      controller: controller,
      validator: validator,
      keyboardType: keyboardType,
      textInputAction: textInputAction,
      obscureText: obscure,
      onFieldSubmitted: onSubmitted,
      inputFormatters: inputFormatters,
      style: const TextStyle(color: AppColors.white),
      decoration: InputDecoration(
        labelText: label,
        labelStyle: const TextStyle(color: AppColors.lightGrey),
        prefixIcon: Icon(icon, color: AppColors.lightGrey, size: 20),
        prefixText: prefixText,
        prefixStyle: const TextStyle(
            color: AppColors.white, fontWeight: FontWeight.w600),
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
        color: color.withOpacity( 0.14),
        borderRadius: BorderRadius.circular(14),
        border: Border.all(color: color.withOpacity( 0.5)),
      ),
      child: Text(
        message,
        style: TextStyle(color: color, fontSize: 13.5, height: 1.35),
      ),
    );
  }
}

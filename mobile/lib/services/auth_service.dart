import 'package:flutter/foundation.dart';
import 'package:supabase_flutter/supabase_flutter.dart';

import 'supabase_service.dart';

/// Erreur d'authentification lisible pour l'UI.
class AuthFailure implements Exception {
  const AuthFailure(this.message);
  final String message;
  @override
  String toString() => message;
}

/// Authentification par **numéro de téléphone + code**, sans e-mail ni SMS.
///
/// Astuce : Supabase authentifie par e-mail/mot de passe. On fabrique donc en
/// interne un e-mail « technique » à partir du numéro (`<digits>@fixpro.app`)
/// et on utilise le code comme mot de passe. L'utilisateur ne voit jamais
/// d'e-mail : il saisit uniquement son numéro et son code.
class AuthService {
  const AuthService();

  static const String _emailDomain = 'fixpro.app';

  bool get isAvailable => SupabaseService.isReady;

  GoTrueClient get _auth => SupabaseService.client.auth;

  Session? get currentSession =>
      SupabaseService.isReady ? _auth.currentSession : null;

  User? get currentUser => SupabaseService.isReady ? _auth.currentUser : null;

  bool get isLoggedIn => currentSession != null;

  void _ensureReady() {
    if (!SupabaseService.isReady) {
      throw const AuthFailure(
        "La connexion au serveur n'est pas configurée.",
      );
    }
  }

  /// Ne garde que les chiffres du numéro saisi.
  static String normalizePhone(String phone) =>
      phone.replaceAll(RegExp(r'\D'), '');

  static String _emailForPhone(String phone) =>
      '${normalizePhone(phone)}@$_emailDomain';

  Future<void> signIn({required String phone, required String code}) async {
    _ensureReady();
    try {
      await _auth.signInWithPassword(
        email: _emailForPhone(phone),
        password: code,
      );
    } on AuthException catch (e) {
      throw AuthFailure(_friendly(e.message));
    }
  }

  Future<void> signUp({
    required String phone,
    required String code,
    required String firstName,
    required String lastName,
  }) async {
    _ensureReady();
    final digits = normalizePhone(phone);
    final fullName = '${firstName.trim()} ${lastName.trim()}'.trim();
    try {
      final res = await _auth.signUp(
        email: _emailForPhone(phone),
        password: code,
        data: {
          'full_name': fullName,
          'first_name': firstName.trim(),
          'last_name': lastName.trim(),
          'phone': digits,
        },
      );
      // Confirmation e-mail désactivée => session immédiate. Par sécurité, si
      // aucune session n'est renvoyée, on tente une connexion directe.
      if (res.session == null) {
        await _auth.signInWithPassword(
          email: _emailForPhone(phone),
          password: code,
        );
      }
    } on AuthException catch (e) {
      throw AuthFailure(_friendly(e.message));
    }
  }

  /// Connexion via Google (OAuth). Sur le web, redirige vers Google puis
  /// revient sur l'application.
  Future<void> signInWithGoogle() async {
    _ensureReady();
    try {
      await _auth.signInWithOAuth(
        OAuthProvider.google,
        redirectTo: kIsWeb ? null : 'io.fixpro://login-callback',
      );
    } on AuthException catch (e) {
      throw AuthFailure(_friendly(e.message));
    }
  }

  Future<void> signOut() async {
    if (!SupabaseService.isReady) return;
    await _auth.signOut();
  }

  String _friendly(String raw) {
    final m = raw.toLowerCase();
    if (m.contains('invalid login')) {
      return 'Numéro ou code incorrect.';
    }
    if (m.contains('already registered') || m.contains('already been')) {
      return 'Ce numéro a déjà un compte. Connecte-toi.';
    }
    if (m.contains('password')) {
      return 'Code trop court (6 caractères minimum).';
    }
    if (m.contains('rate limit')) {
      return 'Trop de tentatives. Réessaie dans quelques minutes.';
    }
    if (m.contains('email') && m.contains('invalid')) {
      return 'Numéro de téléphone invalide.';
    }
    return raw;
  }
}

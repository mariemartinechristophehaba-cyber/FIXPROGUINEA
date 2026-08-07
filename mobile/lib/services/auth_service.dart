import 'package:supabase_flutter/supabase_flutter.dart';

import 'supabase_service.dart';

/// Résultat d'une inscription : indique si une confirmation e-mail est requise.
class SignUpOutcome {
  const SignUpOutcome({required this.needsEmailConfirmation});

  final bool needsEmailConfirmation;
}

/// Erreur d'authentification lisible pour l'UI.
class AuthFailure implements Exception {
  const AuthFailure(this.message);
  final String message;
  @override
  String toString() => message;
}

/// Encapsule l'authentification Supabase (email / mot de passe).
class AuthService {
  const AuthService();

  bool get isAvailable => SupabaseService.isReady;

  GoTrueClient get _auth => SupabaseService.client.auth;

  Session? get currentSession =>
      SupabaseService.isReady ? _auth.currentSession : null;

  User? get currentUser => SupabaseService.isReady ? _auth.currentUser : null;

  bool get isLoggedIn => currentSession != null;

  Stream<AuthState>? get onAuthStateChange =>
      SupabaseService.isReady ? _auth.onAuthStateChange : null;

  void _ensureReady() {
    if (!SupabaseService.isReady) {
      throw const AuthFailure(
        "La connexion au serveur n'est pas configurée.",
      );
    }
  }

  Future<void> signIn({required String email, required String password}) async {
    _ensureReady();
    try {
      await _auth.signInWithPassword(
        email: email.trim(),
        password: password,
      );
    } on AuthException catch (e) {
      throw AuthFailure(_friendly(e.message));
    }
  }

  Future<SignUpOutcome> signUp({
    required String email,
    required String password,
    required String fullName,
  }) async {
    _ensureReady();
    try {
      final res = await _auth.signUp(
        email: email.trim(),
        password: password,
        data: {'full_name': fullName.trim()},
      );
      return SignUpOutcome(needsEmailConfirmation: res.session == null);
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
      return 'E-mail ou mot de passe incorrect.';
    }
    if (m.contains('email not confirmed')) {
      return "E-mail pas encore confirmé. Vérifie ta boîte mail.";
    }
    if (m.contains('already registered') || m.contains('already been')) {
      return 'Un compte existe déjà avec cet e-mail.';
    }
    if (m.contains('password')) {
      return 'Mot de passe trop court (6 caractères minimum).';
    }
    if (m.contains('rate limit')) {
      return 'Trop de tentatives. Réessaie dans quelques minutes.';
    }
    return raw;
  }
}

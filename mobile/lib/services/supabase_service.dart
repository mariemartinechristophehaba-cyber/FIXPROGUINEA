import 'package:supabase_flutter/supabase_flutter.dart';

import '../config/app_config.dart';

/// Point d'accès unique au client Supabase.
///
/// L'initialisation est optionnelle : si les identifiants ne sont pas fournis
/// (`--dart-define`), l'app fonctionne en mode démo avec les données mockées.
class SupabaseService {
  SupabaseService._();

  static bool _initialized = false;

  static bool get isReady => _initialized;

  /// Initialise Supabase si configuré. Sans effet sinon.
  static Future<void> initialize() async {
    if (_initialized || !AppConfig.isSupabaseConfigured) return;
    await Supabase.initialize(
      url: AppConfig.supabaseUrl,
      publishableKey: AppConfig.supabaseAnonKey,
    );
    _initialized = true;
  }

  static SupabaseClient get client => Supabase.instance.client;
}

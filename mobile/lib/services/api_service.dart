import 'dart:convert';
import 'dart:io';
import 'package:http/http.dart' as http;

import '../config/app_config.dart';

/// Service d'acces au backend FixPro Flask.
///
/// L'URL est configurable via `--dart-define=API_URL=...`.
/// Par defaut, il pointe sur le backend local de developpement.
class ApiService {
  ApiService._();

  static final http.Client _client = http.Client();
  static String? _sessionCookie;

  static String get baseUrl =>
      const String.fromEnvironment('API_URL', defaultValue: 'http://10.0.2.2:5000');

  static bool get isConfigured => baseUrl.isNotEmpty;

  static bool get isLoggedIn => _sessionCookie != null && _sessionCookie!.isNotEmpty;

  static void logout() {
    _sessionCookie = null;
  }

  /// Extrait le cookie de session Flask de l'en-tete `Set-Cookie`.
  static String _extractSessionCookie(String? setCookie) {
    if (setCookie == null || setCookie.isEmpty) return '';
    final match = RegExp(r'session=[^;]+').firstMatch(setCookie);
    return match?.group(0) ?? '';
  }

  static void _assertConfigured() {
    if (!isConfigured) {
      throw const ApiFailure('API_URL non configure.');
    }
  }

  /// Connexion a la session Flask via telephone + mot de passe.
  static Future<void> login({
    required String phone,
    required String password,
  }) async {
    _assertConfigured();
    _sessionCookie = null;

    final request = http.Request('POST', Uri.parse('$baseUrl/login'))
      ..followRedirects = false
      ..bodyFields = {'identifier': phone, 'password': password}
      ..headers['Content-Type'] = 'application/x-www-form-urlencoded';

    final streamed = await _client.send(request);
    final response = await http.Response.fromStream(streamed);

    if (response.statusCode >= 300 && response.statusCode < 400) {
      _sessionCookie = _extractSessionCookie(response.headers['set-cookie']);
      if (_sessionCookie == null || _sessionCookie!.isEmpty) {
        throw const ApiFailure('Aucune session recue.');
      }
      return;
    }

    if (response.statusCode >= 400) {
      throw const ApiFailure('Identifiants incorrects.');
    }

    final message = _extractMessage(response.body);
    if (message.toLowerCase().contains('incorrect')) {
      throw const ApiFailure('Identifiants incorrects.');
    }
    throw ApiFailure(message);
  }

  static Future<Map<String, dynamic>> getProfile() async {
    _assertConfigured();
    if (!isLoggedIn) throw const ApiFailure('Session inconnue.');

    final response = await _client.get(
      Uri.parse('$baseUrl/api/technicien/profile'),
      headers: {'Cookie': _sessionCookie!},
    );

    if (response.statusCode >= 400) {
      throw const ApiFailure('Profil introuvable.');
    }
    return jsonDecode(response.body) as Map<String, dynamic>;
  }

  /// Met a jour le statut de disponibilite (en_ligne / occupe / hors_ligne).
  static Future<void> updateAvailability(String status) async {
    _assertConfigured();
    if (!isLoggedIn) throw const ApiFailure('Session inconnue.');

    final request = http.Request('POST', Uri.parse('$baseUrl/api/technicien/status'))
      ..followRedirects = false
      ..bodyFields = {'status': status}
      ..headers['Content-Type'] = 'application/x-www-form-urlencoded'
      ..headers['Cookie'] = _sessionCookie!;

    final streamed = await _client.send(request);
    final response = await http.Response.fromStream(streamed);

    if (response.statusCode >= 400) {
      throw const ApiFailure('Impossible de mettre a jour le statut.');
    }
  }

  /// Envoie la position GPS au backend.
  static Future<bool> sendPosition(double latitude, double longitude) async {
    _assertConfigured();
    if (!isLoggedIn) throw const ApiFailure('Session inconnue.');

    final request = http.Request('POST', Uri.parse('$baseUrl/api/technicien/position'))
      ..followRedirects = false
      ..bodyFields = {'lat': latitude.toString(), 'lon': longitude.toString()}
      ..headers['Content-Type'] = 'application/x-www-form-urlencoded'
      ..headers['Cookie'] = _sessionCookie!;

    final streamed = await _client.send(request);
    final response = await http.Response.fromStream(streamed);

    if (response.statusCode >= 400) {
      throw const ApiFailure('Serveur non joignable.');
    }

    final body = jsonDecode(response.body) as Map<String, dynamic>?;
    if (body != null && body['ok'] == true) return true;

    final reason = body?['reason'] as String?;
    if (reason != null && reason.isNotEmpty) {
      throw ApiFailure(reason);
    }
    return false;
  }

  static Future<void> registerTechnician({
    required String firstName,
    required String lastName,
    required String phone,
    required String password,
    String? email,
    String? profession,
    String? city,
    String? quartier,
    String? bio,
    String? identityDoc,
    String? diplomaDoc,
  }) async {
    _assertConfigured();

    final body = {
      'first_name': firstName,
      'last_name': lastName,
      'phone': phone,
      'password': password,
      if (email != null && email.isNotEmpty) 'email': email,
      if (profession != null && profession.isNotEmpty) 'profession': profession,
      if (city != null && city.isNotEmpty) 'city': city,
      if (quartier != null && quartier.isNotEmpty) 'quartier': quartier,
      if (bio != null && bio.isNotEmpty) 'bio': bio,
      if (identityDoc != null && identityDoc.isNotEmpty) 'identity_doc': identityDoc,
      if (diplomaDoc != null && diplomaDoc.isNotEmpty) 'diploma_doc': diplomaDoc,
    };

    final response = await _client.post(
      Uri.parse('$baseUrl/api/mobile/register'),
      headers: {'Content-Type': 'application/json'},
      body: jsonEncode(body),
    );

    if (response.statusCode >= 400) {
      final message = _extractMessage(response.body);
      throw ApiFailure(message);
    }
  }

  /// Liste les techniciens actifs et verifies depuis le backend.
  static Future<List<Map<String, dynamic>>> getTechnicians() async {
    _assertConfigured();
    final response = await _client.get(
      Uri.parse('$baseUrl/api/techniciens'),
    );
    if (response.statusCode >= 400) {
      throw ApiFailure(_extractMessage(response.body));
    }
    final body = jsonDecode(response.body) as Map<String, dynamic>;
    final data = (body['technicians'] as List<dynamic>? ?? [])
        .cast<Map<String, dynamic>>();
    return data;
  }

  static String _extractMessage(String body) {
    try {
      final decoded = jsonDecode(body) as Map<String, dynamic>?;
      return decoded?['error']?.toString() ?? 'Erreur inconnue';
    } catch (_) {
      return 'Erreur reseau (${body.length} octets)';
    }
  }
}

class ApiFailure implements Exception {
  const ApiFailure(this.message);
  final String message;
  @override
  String toString() => message;
}

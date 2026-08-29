import 'dart:convert';
import 'dart:io';
import 'package:http/http.dart' as http;

import '../config/app_config.dart';
import 'token_service.dart';

/// Service d'acces au backend FixPro Flask.
///
/// L'URL est configurable via `--dart-define=API_URL=...`.
/// Par defaut, il pointe sur le backend local de developpement.
class ApiService {
  ApiService._();

  static final http.Client _client = http.Client();

  static String get baseUrl =>
      const String.fromEnvironment('API_URL', defaultValue: 'http://10.0.2.2:5000');

  static bool get isConfigured => baseUrl.isNotEmpty;

  static Future<bool> get isLoggedIn async {
    final token = await TokenService.getToken();
    return token != null && token.isNotEmpty;
  }

  static void logout() {
    TokenService.clearAll();
  }

  static void _assertConfigured() {
    if (!isConfigured) {
      throw const ApiFailure('API_URL non configure.');
    }
  }

  /// Verifie si une session mobile est encore valide.
  static Future<Map<String, dynamic>?> verifySession() async {
    await _assertConfigured();
    final token = await TokenService.getToken();
    if (token == null || token.isEmpty) return null;

    final response = await _client.get(
      Uri.parse('$baseUrl/api/mobile/verify'),
      headers: {'Authorization': 'Bearer $token'},
    );

    if (response.statusCode == 200) {
      final body = jsonDecode(response.body) as Map<String, dynamic>;
      final user = body['user'] as Map<String, dynamic>?;
      if (user != null) {
        await TokenService.setUser(jsonEncode(user));
      }
      return user;
    }

    if (response.statusCode == 401) {
      await TokenService.clearAll();
    }
    return null;
  }

  /// Connexion d'un technicien et stockage securise du token 7 jours.
  static Future<void> login({
    required String phone,
    required String password,
  }) async {
    await _assertConfigured();
    await TokenService.clearAll();

    final response = await _client.post(
      Uri.parse('$baseUrl/api/mobile/login'),
      headers: {'Content-Type': 'application/json'},
      body: jsonEncode({'phone': phone, 'password': password}),
    );

    if (response.statusCode >= 400) {
      final message = _extractMessage(response.body);
      throw ApiFailure(message);
    }

    final body = jsonDecode(response.body) as Map<String, dynamic>;
    final token = body['token'] as String?;
    final user = body['user'] as Map<String, dynamic>?;

    if (token == null || token.isEmpty || user == null) {
      throw const ApiFailure('Reponse de connexion incomplete.');
    }

    await TokenService.setToken(token);
    await TokenService.setUser(jsonEncode(user));
  }

  static Future<Map<String, dynamic>> getProfile() async {
    await _assertConfigured();
    if (!await isLoggedIn) throw const ApiFailure('Session inconnue.');

    final token = await TokenService.getToken();
    final response = await _client.get(
      Uri.parse('$baseUrl/api/technicien/profile'),
      headers: {'Authorization': 'Bearer $token'},
    );

    if (response.statusCode >= 400) {
      throw const ApiFailure('Profil introuvable.');
    }
    return jsonDecode(response.body) as Map<String, dynamic>;
  }

  /// Met a jour le statut de disponibilite (en_ligne / occupe / hors_ligne).
  static Future<void> updateAvailability(String status) async {
    await _assertConfigured();
    if (!await isLoggedIn) throw const ApiFailure('Session inconnue.');

    final token = await TokenService.getToken();
    final response = await _client.post(
      Uri.parse('$baseUrl/api/technicien/status'),
      headers: {
        'Content-Type': 'application/x-www-form-urlencoded',
        'Authorization': 'Bearer $token',
      },
      body: {'status': status},
    );

    if (response.statusCode >= 400) {
      throw const ApiFailure('Impossible de mettre a jour le statut.');
    }
  }

  /// Envoie la position GPS au backend.
  static Future<bool> sendPosition(double latitude, double longitude) async {
    await _assertConfigured();
    if (!await isLoggedIn) throw const ApiFailure('Session inconnue.');

    final token = await TokenService.getToken();
    final response = await _client.post(
      Uri.parse('$baseUrl/api/technicien/position'),
      headers: {
        'Content-Type': 'application/x-www-form-urlencoded',
        'Authorization': 'Bearer $token',
      },
      body: {'lat': latitude.toString(), 'lon': longitude.toString()},
    );

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
    await _assertConfigured();

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
    await _assertConfigured();
    final response = await _client.get(Uri.parse('$baseUrl/api/techniciens'));
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

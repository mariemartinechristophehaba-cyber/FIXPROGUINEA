import 'dart:async';
import 'package:flutter/material.dart';
import 'package:geolocator/geolocator.dart';

import '../services/api_service.dart';
import '../theme/app_colors.dart';
import '../widgets/common.dart';
import '../widgets/glass_card.dart';
import 'welcome_screen.dart';

/// Dashboard minimal reserve au technicien.
///
/// - Affiche le statut En ligne / Hors ligne.
/// - Envoie la position GPS au backend quand le technicien est en ligne.
/// - Respecte les permissions et le service de localisation Android/iOS.
class TechnicianDashboardScreen extends StatefulWidget {
  const TechnicianDashboardScreen({super.key});

  @override
  State<TechnicianDashboardScreen> createState() => _TechnicianDashboardScreenState();
}

class _TechnicianDashboardScreenState extends State<TechnicianDashboardScreen> {
  Map<String, dynamic>? _profile;
  bool _loading = true;
  String? _error;
  String _status = 'hors_ligne';
  Timer? _gpsTimer;
  String? _lastMessage;
  bool _permissionDenied = false;
  bool _serviceDisabled = false;

  static const _gpsInterval = Duration(seconds: 20);

  @override
  void initState() {
    super.initState();
    _loadProfile();
  }

  @override
  void dispose() {
    _stopGps();
    super.dispose();
  }

  Future<void> _loadProfile() async {
    try {
      final profile = await ApiService.getProfile();
      setState(() {
        _profile = profile;
        _status = (profile['availability_status'] as String?) ?? 'hors_ligne';
        _loading = false;
      });
      if (_status == 'en_ligne') {
        await _startGps();
      }
    } on ApiFailure catch (e) {
      setState(() {
        _error = e.message;
        _loading = false;
      });
    }
  }

  Future<void> _setStatus(String status) async {
    setState(() {
      _status = status;
      _lastMessage = 'Mise a jour du statut...';
    });
    try {
      await ApiService.updateAvailability(status);
      if (status == 'en_ligne') {
        await _startGps();
      } else {
        _stopGps();
      }
      setState(() => _lastMessage = 'Statut : $_status');
    } on ApiFailure catch (e) {
      setState(() => _error = e.message);
    }
  }

  Future<void> _startGps() async {
    _stopGps();

    final enabled = await Geolocator.isLocationServiceEnabled();
    if (!enabled) {
      setState(() {
        _serviceDisabled = true;
        _lastMessage = 'GPS desactive. Activez-le pour recevoir des missions.';
      });
      return;
    }
    setState(() => _serviceDisabled = false);

    var permission = await Geolocator.checkPermission();
    if (permission == LocationPermission.denied) {
      permission = await Geolocator.requestPermission();
    }

    if (permission == LocationPermission.denied) {
      setState(() {
        _permissionDenied = true;
        _lastMessage = 'Permission de localisation refusee.';
      });
      return;
    }

    if (permission == LocationPermission.deniedForever) {
      setState(() {
        _permissionDenied = true;
        _lastMessage = 'Permission refusee definitivement. Activez-la dans les parametres.';
      });
      return;
    }

    setState(() {
      _permissionDenied = false;
      _lastMessage = 'GPS actif. Envoi en cours...';
    });

    await _sendGps();
    _gpsTimer = Timer.periodic(_gpsInterval, (_) => _sendGps());
  }

  void _stopGps() {
    _gpsTimer?.cancel();
    _gpsTimer = null;
  }

  Future<void> _sendGps() async {
    try {
      final position = await Geolocator.getCurrentPosition(
        desiredAccuracy: LocationAccuracy.best,
      );
      await ApiService.sendPosition(position.latitude, position.longitude);
      setState(() {
        _lastMessage =
            'Position envoyee : ${position.latitude.toStringAsFixed(5)}, ${position.longitude.toStringAsFixed(5)}';
      });
    } on ApiFailure catch (e) {
      setState(() => _lastMessage = 'Erreur envoi : ${e.message}');
    } catch (e) {
      setState(() => _lastMessage = 'Erreur GPS : $e');
    }
  }

  Future<void> _logout() async {
    _stopGps();
    ApiService.logout();
    if (!mounted) return;
    Navigator.of(context).pushAndRemoveUntil(
      MaterialPageRoute(builder: (_) => const WelcomeScreen()),
      (route) => false,
    );
  }

  @override
  Widget build(BuildContext context) {
    final textTheme = Theme.of(context).textTheme;

    if (_loading) {
      return const Scaffold(
        body: Center(child: CircularProgressIndicator()),
      );
    }

    if (_error != null) {
      return Scaffold(
        body: Center(child: Text(_error!, style: const TextStyle(color: Colors.white))),
      );
    }

    final name = _profile?['full_name'] as String? ?? 'Technicien';
    final profession = _profile?['profession'] as String? ?? '';
    final isOnline = _status == 'en_ligne';

    return Scaffold(
      body: DecoratedBox(
        decoration: const BoxDecoration(gradient: AppColors.backgroundGradient),
        child: SafeArea(
          child: Padding(
            padding: const EdgeInsets.symmetric(horizontal: 24),
            child: ListView(
              children: [
                const SizedBox(height: 24),
                Row(
                  children: [
                    Expanded(
                      child: Column(
                        crossAxisAlignment: CrossAxisAlignment.start,
                        children: [
                          Text(
                            'Bonjour $name',
                            style: textTheme.headlineSmall?.copyWith(fontSize: 24),
                          ),
                          const SizedBox(height: 4),
                          Text(
                            profession,
                            style: textTheme.bodyMedium?.copyWith(
                              color: AppColors.lightGrey,
                              fontSize: 14,
                            ),
                          ),
                        ],
                      ),
                    ),
                    IconButton(
                      icon: const Icon(Icons.logout_rounded, color: AppColors.white),
                      onPressed: _logout,
                    ),
                  ],
                ),
                const SizedBox(height: 28),
                GlassCard(
                  padding: const EdgeInsets.all(20),
                  radius: 24,
                  child: Column(
                    crossAxisAlignment: CrossAxisAlignment.start,
                    children: [
                      Text(
                        'Disponibilite',
                        style: textTheme.titleLarge?.copyWith(fontSize: 18),
                      ),
                      const SizedBox(height: 18),
                      Row(
                        children: [
                          Container(
                            width: 12,
                            height: 12,
                            decoration: BoxDecoration(
                              color: isOnline ? Colors.green : AppColors.lightGrey,
                              shape: BoxShape.circle,
                            ),
                          ),
                          const SizedBox(width: 10),
                          Expanded(
                            child: Text(
                              isOnline ? 'En ligne' : 'Hors ligne',
                              style: textTheme.bodyLarge?.copyWith(fontSize: 16),
                            ),
                          ),
                          Switch(
                            value: isOnline,
                            onChanged: (v) => _setStatus(v ? 'en_ligne' : 'hors_ligne'),
                            activeColor: Colors.green,
                          ),
                        ],
                      ),
                    ],
                  ),
                ),
                const SizedBox(height: 20),
                if (isOnline)
                  GlassCard(
                    padding: const EdgeInsets.all(20),
                    radius: 24,
                    child: Column(
                      crossAxisAlignment: CrossAxisAlignment.start,
                      children: [
                        Text(
                          'GPS',
                          style: textTheme.titleLarge?.copyWith(fontSize: 18),
                        ),
                        const SizedBox(height: 12),
                        Text(
                          _lastMessage ?? 'En attente...',
                          style: textTheme.bodyMedium?.copyWith(fontSize: 14),
                        ),
                        if (_serviceDisabled)
                          _Message(
                            text: 'Le service de localisation est desactive.',
                            color: AppColors.red,
                          ),
                        if (_permissionDenied)
                          _Message(
                            text: 'Autorisez la localisation pour envoyer votre position.',
                            color: AppColors.red,
                          ),
                      ],
                    ),
                  ),
                if (!isOnline)
                  Padding(
                    padding: const EdgeInsets.only(top: 12),
                    child: Text(
                      'Passez en ligne pour activer le GPS et recevoir des missions.',
                      style: textTheme.bodyMedium?.copyWith(
                        color: AppColors.lightGrey,
                        fontSize: 13,
                      ),
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

class _Message extends StatelessWidget {
  const _Message({required this.text, required this.color});

  final String text;
  final Color color;

  @override
  Widget build(BuildContext context) {
    return Padding(
      padding: const EdgeInsets.only(top: 10),
      child: Text(
        text,
        style: TextStyle(color: color, fontSize: 13),
      ),
    );
  }
}

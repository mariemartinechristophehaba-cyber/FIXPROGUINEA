import 'package:flutter/material.dart';

/// Catégorie de métier affichée dans la grille du tableau de bord.
class ServiceCategory {
  const ServiceCategory({
    required this.label,
    required this.emoji,
    required this.icon,
    required this.technicianCount,
  });

  final String label;
  final String emoji;
  final IconData icon;
  final int technicianCount;
}

/// Carte de statistique du tableau de bord client.
class DashboardStat {
  const DashboardStat({
    required this.emoji,
    required this.title,
    required this.value,
    required this.trend,
    required this.accent,
  });

  final String emoji;
  final String title;
  final String value;
  final String trend;
  final Color accent;
}

/// Technicien affiché dans la liste "près de vous" et la fiche détaillée.
class Technician {
  const Technician({
    required this.name,
    required this.job,
    required this.icon,
    required this.rating,
    required this.distanceKm,
    required this.hourlyRate,
    this.reviewCount = 0,
    this.interventions = 0,
    this.experienceYears = 0,
    this.about = '',
  });

  final String name;
  final String job;
  final IconData icon;
  final double rating;
  final double distanceKm;
  final int hourlyRate;
  final int reviewCount;
  final int interventions;
  final int experienceYears;
  final String about;

  /// Initiales pour l'avatar rond.
  String get initials {
    final parts = name.trim().split(' ');
    if (parts.length == 1) return parts.first.substring(0, 1).toUpperCase();
    return (parts.first.substring(0, 1) + parts.last.substring(0, 1))
        .toUpperCase();
  }

  /// Construit un technicien depuis une ligne de la table `profiles` Supabase.
  factory Technician.fromProfile(Map<String, dynamic> row) {
    final profession = (row['profession'] as String?)?.trim();
    return Technician(
      name: (row['full_name'] as String?)?.trim().isNotEmpty == true
          ? row['full_name'] as String
          : 'Technicien',
      job: profession?.isNotEmpty == true ? profession! : 'Technicien',
      icon: iconForProfession(profession),
      rating: _toDouble(row['rating']),
      distanceKm: _toDouble(row['distance_km']),
      hourlyRate: _toDouble(row['hourly_rate']).round(),
      reviewCount: _toInt(row['review_count']),
      interventions: _toInt(row['interventions']),
      experienceYears: _toInt(row['experience_years']),
      about: (row['bio'] as String?)?.trim() ?? '',
    );
  }

  static double _toDouble(Object? v) =>
      v == null ? 0 : (v is num ? v.toDouble() : double.tryParse('$v') ?? 0);

  static int _toInt(Object? v) =>
      v == null ? 0 : (v is num ? v.toInt() : int.tryParse('$v') ?? 0);
}

/// Associe un métier (profession) à une icône Material.
IconData iconForProfession(String? profession) {
  final p = (profession ?? '').toLowerCase();
  if (p.contains('plomb')) return Icons.plumbing;
  if (p.contains('élec') || p.contains('elec')) return Icons.electrical_services;
  if (p.contains('froid') || p.contains('clim') || p.contains('frigo')) {
    return Icons.ac_unit;
  }
  if (p.contains('maçon') || p.contains('macon') || p.contains('bâtiment')) {
    return Icons.construction;
  }
  return Icons.handyman;
}

/// Statut d'un contrat récent.
enum ContractStatus { termine, enCours, planifie }

extension ContractStatusView on ContractStatus {
  String get label => switch (this) {
        ContractStatus.termine => 'Terminé',
        ContractStatus.enCours => 'En cours',
        ContractStatus.planifie => 'Planifié',
      };

  String get emoji => switch (this) {
        ContractStatus.termine => '🟢',
        ContractStatus.enCours => '🟠',
        ContractStatus.planifie => '🔵',
      };

  Color get color => switch (this) {
        ContractStatus.termine => const Color(0xFF28C76F),
        ContractStatus.enCours => const Color(0xFFF5A623),
        ContractStatus.planifie => const Color(0xFF2E5BFF),
      };
}

/// Contrat récent affiché dans la section "Mes contrats récents".
class Contract {
  const Contract({
    required this.title,
    required this.technicianName,
    required this.date,
    required this.amount,
    required this.status,
  });

  final String title;
  final String technicianName;
  final String date;
  final String amount;
  final ContractStatus status;
}

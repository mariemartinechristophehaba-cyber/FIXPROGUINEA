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

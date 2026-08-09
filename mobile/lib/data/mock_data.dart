import 'package:flutter/material.dart';

import '../models/models.dart';
import '../theme/app_colors.dart';

/// Données de démonstration.
///
/// Structurées pour être facilement remplacées par un appel Firebase / API REST
/// (chaque liste correspondrait à une collection ou un endpoint).
class MockData {
  MockData._();

  static const List<ServiceCategory> categories = [
    ServiceCategory(
      label: 'Plomberie',
      emoji: '🔧',
      icon: Icons.plumbing,
      technicianCount: 48,
    ),
    ServiceCategory(
      label: 'Électricité',
      emoji: '⚡',
      icon: Icons.electrical_services,
      technicianCount: 62,
    ),
    ServiceCategory(
      label: 'Froid & Clim',
      emoji: '❄️',
      icon: Icons.ac_unit,
      technicianCount: 35,
    ),
    ServiceCategory(
      label: 'Maçonnerie',
      emoji: '🏗️',
      icon: Icons.construction,
      technicianCount: 41,
    ),
  ];

  static const List<DashboardStat> stats = [
    DashboardStat(
      emoji: '📋',
      title: 'Contrats en cours',
      value: '3',
      trend: '↑ 1 nouveau',
      accent: AppColors.primaryBlue,
    ),
    DashboardStat(
      emoji: '✅',
      title: 'Travaux terminés',
      value: '12',
      trend: '↑ Depuis janvier',
      accent: AppColors.green,
    ),
    DashboardStat(
      emoji: '⭐',
      title: 'Note moyenne',
      value: '4.8',
      trend: '↑ Excellent',
      accent: AppColors.orange,
    ),
    DashboardStat(
      emoji: '💰',
      title: 'Dépenses',
      value: '1.2 M GNF',
      trend: 'Ce mois : 350 000 GNF',
      accent: AppColors.red,
    ),
  ];

  static const List<Technician> technicians = [
    Technician(
      name: 'Ibrahima Bah',
      job: 'Électricien',
      icon: Icons.electrical_services,
      rating: 4.9,
      distanceKm: 1.2,
      hourlyRate: 50000,
      reviewCount: 128,
      interventions: 210,
      experienceYears: 8,
      about:
          "Électricien certifié spécialisé dans les installations résidentielles "
          "et le dépannage d'urgence à Conakry. Rapide, fiable et minutieux.",
    ),
    Technician(
      name: 'Mamadou Camara',
      job: 'Plombier',
      icon: Icons.plumbing,
      rating: 4.7,
      distanceKm: 2.5,
      hourlyRate: 40000,
      reviewCount: 96,
      interventions: 174,
      experienceYears: 6,
      about:
          "Plombier expérimenté : réparation de fuites, installation sanitaire "
          "et entretien de canalisations. Intervention soignée et durable.",
    ),
    Technician(
      name: 'Sékou Diallo',
      job: 'Frigoriste',
      icon: Icons.ac_unit,
      rating: 4.8,
      distanceKm: 3.1,
      hourlyRate: 60000,
      reviewCount: 112,
      interventions: 189,
      experienceYears: 9,
      about:
          "Frigoriste spécialisé en climatisation et chambres froides. "
          "Diagnostic précis et maintenance préventive de qualité.",
    ),
    Technician(
      name: 'Aliou Kouyaté',
      job: 'Maçon',
      icon: Icons.construction,
      rating: 4.5,
      distanceKm: 4.0,
      hourlyRate: 35000,
      reviewCount: 74,
      interventions: 143,
      experienceYears: 12,
      about:
          "Maçon polyvalent : gros œuvre, finitions et rénovation. "
          "Travail solide, respect des délais et du budget.",
    ),
  ];

  static const List<Contract> recentContracts = [
    Contract(
      title: 'Installation électrique',
      technicianName: 'Ibrahima Bah',
      date: '02 Mai 2026',
      amount: '150 000 GNF',
      status: ContractStatus.termine,
    ),
    Contract(
      title: 'Réparation tuyau',
      technicianName: 'Mamadou Camara',
      date: '05 Mai 2026',
      amount: '80 000 GNF',
      status: ContractStatus.enCours,
    ),
    Contract(
      title: 'Entretien climatiseur',
      technicianName: 'Sékou Diallo',
      date: '06 Mai 2026',
      amount: '120 000 GNF',
      status: ContractStatus.planifie,
    ),
  ];
}
